"""Notion connector: read databases and pages with an internal integration token.

Plain HTTPS, no SDK. A sync writes Doc nodes, links the page creator (matched by email or
display name to a Person already in the graph, or added as a new Person), and may link ABOUT
a System when the title names exactly one known system. It never writes OWNS or PROPOSES.
Re-running a sync is a MERGE on the Notion page id, the URL, or an existing Doc name.
"""
import datetime
import json
import os
import re
import urllib.error
import urllib.request

import db
import loader
import names
from companies import slugify

API = os.environ.get("NOTION_API", "https://api.notion.com/v1")
VERSION = "2022-06-28"
MAX_DATABASES = 25
PAGE_LIMITS = (10, 20, 50)
DEFAULT_PAGE_LIMIT = 20
DB_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class NotionError(Exception):
    def __init__(self, message, status=0):
        super().__init__(message)
        self.status = status


def env_token():
    return (os.environ.get("NOTION_TOKEN") or os.environ.get("NOTION_API_KEY") or "").strip()


def token_for(cfg):
    return ((cfg or {}).get("token") or "").strip() or env_token()


def database_ids(raw):
    out = []
    for k in raw or []:
        k = (k or "").strip().replace(" ", "")
        if DB_ID.match(k) and k not in out:
            out.append(k)
        if len(out) >= MAX_DATABASES:
            break
    return out


def call(token, method, path, body=None):
    token = (token or "").strip()
    if not token:
        raise NotionError("Paste a Notion internal integration token from notion.so/my-integrations.")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method, headers={
        "Authorization": f"Bearer {token}", "Notion-Version": VERSION,
        "Content-Type": "application/json", "User-Agent": "graph-desk/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=25) as res:
            raw = res.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as err:
        raise NotionError(_explain(err), err.code) from err
    except (urllib.error.URLError, TimeoutError) as err:
        raise NotionError(f"Could not reach Notion: {getattr(err, 'reason', err)}") from err


def _explain(err):
    try:
        detail = json.loads(err.read().decode("utf-8", errors="replace"))
        msg = detail.get("message") or ""
    except (ValueError, OSError):
        msg = ""
    if err.code == 401:
        return "Notion rejected the token. Copy the internal integration secret in full."
    if err.code == 403:
        return f"Notion refused: {msg or 'share the database with the integration'}."
    if err.code == 404:
        return "Notion could not find that database, or it is not shared with this integration."
    return f"Notion said {err.code}: {msg}".strip()


def _plain(rich):
    if isinstance(rich, str):
        return rich
    return "".join((t.get("plain_text") or "") for t in (rich or []))


def _user(u):
    if not u or u.get("type") == "bot" or u.get("object") == "bot":
        return None
    email = ((u.get("person") or {}).get("email") or "").lower()
    name = u.get("name") or ""
    if not name and not email:
        return None
    return {"id": u.get("id") or "", "name": name, "email": email}


def _page_title(page):
    for p in (page.get("properties") or {}).values():
        if p.get("type") == "title":
            return _plain(p.get("title"))
    return _plain(page.get("title"))


def verify(token):
    me = call(token, "GET", "/users/me")
    bot = me.get("bot") or {}
    name = me.get("name") or bot.get("workspace_name") or "Notion"
    email = ((me.get("person") or {}).get("email") or "")
    return {"id": me.get("id") or "", "name": name, "email": email,
            "workspace": bot.get("workspace_name") or ""}


def list_databases(token):
    out, cursor = [], None
    for _ in range(5):
        body = {"filter": {"property": "object", "value": "database"}, "page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        page = call(token, "POST", "/search", body)
        for row in page.get("results") or []:
            if row.get("object") != "database" or not row.get("id"):
                continue
            out.append({"id": row["id"], "name": _plain(row.get("title")) or "Untitled",
                        "url": row.get("url") or ""})
        if not page.get("has_more"):
            break
        cursor = page.get("next_cursor")
        if not cursor:
            break
    return out


def fetch_database(token, db_id, limit):
    if not DB_ID.match(db_id or ""):
        raise NotionError(f"{db_id}: not a database id.")
    body = call(token, "POST", f"/databases/{db_id}/query",
                {"page_size": min(limit, 100),
                 "sorts": [{"timestamp": "last_edited_time", "direction": "descending"}]})
    pages = []
    for p in (body.get("results") or [])[:limit]:
        pages.append({
            "id": p.get("id") or "",
            "title": _page_title(p) or "Untitled",
            "url": p.get("url") or "",
            "opened": (p.get("created_time") or "")[:10],
            "author": _user(p.get("created_by")),
        })
    return {"id": db_id, "pages": pages}


def build_bundle(fetched, g):
    email_idx, name_idx = {}, {}
    for pid, email, pname in db.read("MATCH (p:Person) RETURN p.id, p.email, p.name", None, g):
        if email:
            email_idx[str(email).lower()] = pid
        if pname:
            name_idx[str(pname).lower()] = pid
    known = set(email_idx) | set(name_idx)
    by_notion, by_url, by_name = {}, {}, {}
    for did, nid, url, dname, dtitle in db.read(
            "MATCH (d:Doc) RETURN d.id, d.notion, d.url, d.name, d.title", None, g):
        if nid:
            by_notion[str(nid)] = did
        if url:
            by_url[str(url).lower()] = did
        if dname:
            by_name[str(dname).lower()] = did
        if dtitle:
            by_name[str(dtitle).lower()] = did
    systems = [(sid, sname) for sid, sname in db.read("MATCH (s:System) RETURN s.id, s.name", None, g)]
    aliases = {sname: names.system_aliases(sname) for _, sname in systems}
    name_to_id = {sname: sid for sid, sname in systems}

    nodes, links, link_keys = {}, [], set()
    added_people, linked_people, doc_count = [], set(), 0

    def node(label, nid, name, **props):
        nodes.setdefault((label, nid), {"label": label, "id": nid, "props": {"name": name, "source": "notion", **props}})

    def link(src, rel, dst, **props):
        key = (src, rel, dst)
        if key not in link_keys:
            link_keys.add(key)
            links.append({"src": list(src), "rel": rel, "dst": list(dst), "props": props})

    def person(u):
        if not u:
            return None
        pid = (email_idx.get(u["email"]) if u["email"] else None) or name_idx.get(u["name"].lower())
        if pid:
            if (u["email"] in known) or (u["name"].lower() in known):
                linked_people.add(pid)
            return pid
        pid = "notion-" + slugify(u["id"] or u["name"] or "user")
        node("Person", pid, u["name"] or u["email"] or pid, email=u["email"], notion=u["id"])
        if u["email"]:
            email_idx[u["email"]] = pid
        if u["name"]:
            name_idx[u["name"].lower()] = pid
        added_people.append(u["name"] or u["email"] or pid)
        return pid

    def system_in(title):
        hits = names.find_in_text(title, aliases)
        return name_to_id[hits[0]] if len(hits) == 1 else None

    for dbrow in fetched:
        for p in dbrow["pages"]:
            if not p["id"] and not p["title"]:
                continue
            did = (by_notion.get(p["id"]) or by_url.get((p["url"] or "").lower())
                   or by_name.get(p["title"].lower()) or f"notion-{slugify(p['id'] or p['title'])}")
            by_notion[p["id"]] = did
            by_name[p["title"].lower()] = did
            node("Doc", did, p["title"], title=p["title"], date=p["opened"], url=p["url"], notion=p["id"])
            who = person(p["author"])
            if who:
                link(("Person", who), "AUTHORED", ("Doc", did))
            sid = system_in(p["title"])
            if sid:
                link(("Doc", did), "ABOUT", ("System", sid))
            doc_count += 1
    return ({"nodes": list(nodes.values()), "links": links},
            {"docs": doc_count, "people_linked": len(linked_people), "people_added": added_people})


def sync(cfg, g, selected=None):
    keys = database_ids(selected if selected is not None else cfg.get("databases", []))
    limit = cfg.get("page_limit") if cfg.get("page_limit") in PAGE_LIMITS else DEFAULT_PAGE_LIMIT
    if not keys:
        raise NotionError("Pick at least one database to sync.")
    token = token_for(cfg)
    fetched, errors = [], []
    for key in keys:
        try:
            fetched.append(fetch_database(token, key, limit))
        except NotionError as err:
            errors.append(f"{key}: {err}")
    if not fetched:
        raise NotionError(errors[0] if errors else "Nothing to sync.")
    bundle, stats = build_bundle(fetched, g)
    assert not any(l["rel"] in ("OWNS", "PROPOSES") for l in bundle["links"])
    totals = loader.load_bundle(bundle, g)
    return {"at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "databases": len(fetched), "docs": stats["docs"], "people_linked": stats["people_linked"],
            "people_added": stats["people_added"], "nodes": totals["nodes"], "links": totals["links"],
            "errors": errors}
