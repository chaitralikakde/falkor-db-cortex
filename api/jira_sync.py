"""Jira connector: read projects and issues with a Cloud API token.

Plain HTTPS, no SDK. A sync writes Ticket nodes, links the assignee and reporter (matched by
email or display name to a Person already in the graph, or added as a new Person), and may
link ABOUT a System when the summary names exactly one known system. It never writes OWNS
or PROPOSES. Re-running a sync is a MERGE on the ticket key.
"""
import base64
import datetime
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

import db
import loader
import names
from companies import slugify

MAX_PROJECTS = 25
ISSUE_LIMITS = (10, 20, 50)
DEFAULT_ISSUE_LIMIT = 20
PROJECT_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_]+$")


def project_keys(raw):
    out = []
    for k in raw or []:
        k = (k or "").strip()
        if PROJECT_KEY.match(k) and k not in out:
            out.append(k)
        if len(out) >= MAX_PROJECTS:
            break
    return out


class JiraError(Exception):
    def __init__(self, message, status=0):
        super().__init__(message)
        self.status = status


def env_creds():
    site = (os.environ.get("JIRA_SITE") or os.environ.get("JIRA_BASE_URL") or "").strip().rstrip("/")
    email = (os.environ.get("JIRA_EMAIL") or "").strip()
    token = (os.environ.get("JIRA_API_TOKEN") or os.environ.get("JIRA_TOKEN") or "").strip()
    if site and email and token:
        return {"site": site, "email": email, "token": token}
    return None


def creds_for(cfg):
    """Stored site/email/token, filling blanks from the server environment."""
    env = env_creds() or {}
    site = ((cfg or {}).get("site") or env.get("site") or "").strip().rstrip("/")
    email = ((cfg or {}).get("email") or env.get("email") or "").strip()
    token = ((cfg or {}).get("token") or env.get("token") or "").strip()
    return {"site": site, "email": email, "token": token}


def _site(raw):
    s = (raw or "").strip().rstrip("/")
    local = "127.0.0.1" in s or "localhost" in s
    if s.startswith("http://") and not local:
        s = "https://" + s[len("http://"):]
    elif s and not s.startswith(("http://", "https://")):
        s = "https://" + s
    return s


def call(cfg, method, path, params=None, body=None):
    site = _site(cfg["site"])
    if not site:
        raise JiraError("Paste the site URL, for example https://your-team.atlassian.net")
    url = site + path
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    data = json.dumps(body).encode() if body is not None else None
    auth = base64.b64encode(f"{cfg['email']}:{cfg['token']}".encode()).decode()
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Basic {auth}", "Accept": "application/json",
        "Content-Type": "application/json", "User-Agent": "graph-desk/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=25) as res:
            raw = res.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as err:
        raise JiraError(_explain(err), err.code) from err
    except (urllib.error.URLError, TimeoutError) as err:
        raise JiraError(f"Could not reach Jira: {getattr(err, 'reason', err)}") from err


def _explain(err):
    try:
        detail = json.loads(err.read().decode("utf-8", errors="replace"))
        msg = detail.get("message") or (detail.get("errorMessages") or [""])[0]
    except (ValueError, OSError):
        msg = ""
    if err.code == 401:
        return "Jira rejected the email or token. Create an API token at id.atlassian.com and use the account email."
    if err.code == 403:
        return f"Jira refused: {msg or 'this account cannot read those projects'}."
    if err.code == 404:
        return "Jira could not find that site or project. Check the URL ends with .atlassian.net."
    return f"Jira said {err.code}: {msg}".strip()


def verify(cfg):
    c = {**cfg, "site": _site(cfg.get("site")), "email": (cfg.get("email") or "").strip(),
         "token": (cfg.get("token") or "").strip()}
    if not c["email"] or "@" not in c["email"]:
        raise JiraError("Paste the Atlassian account email.")
    if not c["token"]:
        raise JiraError("Paste a Jira API token from id.atlassian.com → Security → API tokens.")
    me = call(c, "GET", "/rest/api/3/myself")
    return {"site": c["site"], "email": me.get("emailAddress") or c["email"],
            "name": me.get("displayName") or "", "account_id": me.get("accountId") or ""}


def list_projects(cfg):
    out, start = [], 0
    for _ in range(5):
        page = call(cfg, "GET", "/rest/api/3/project/search",
                    {"maxResults": 50, "startAt": start, "orderBy": "key"})
        for p in page.get("values") or []:
            out.append({"key": p["key"], "name": p.get("name") or p["key"],
                        "type": p.get("projectTypeKey") or "",
                        "url": f"{_site(cfg['site'])}/browse/{p['key']}"})
        start += len(page.get("values") or [])
        if start >= page.get("total", start) or not page.get("values"):
            break
    return out


def _user(u):
    if not u or u.get("accountType") == "app":
        return None
    return {"account_id": u.get("accountId") or "", "name": u.get("displayName") or "",
            "email": (u.get("emailAddress") or "").lower()}


def fetch_project(cfg, key, limit):
    if not PROJECT_KEY.match(key or ""):
        raise JiraError(f"{key}: not a project key.")
    fields = "summary,status,assignee,reporter,created,updated"
    jql = f'project = "{key}" ORDER BY updated DESC'
    try:
        body = call(cfg, "POST", "/rest/api/3/search/jql",
                    body={"jql": jql, "maxResults": min(limit, 100), "fields": fields.split(",")})
    except JiraError as err:
        if err.status not in (404, 410):
            raise
        body = call(cfg, "GET", "/rest/api/3/search",
                    {"jql": jql, "maxResults": min(limit, 100), "fields": fields})
    issues = []
    for it in (body.get("issues") or [])[:limit]:
        f = it.get("fields") or {}
        status = ((f.get("status") or {}).get("name") or "").lower()
        issues.append({
            "key": it.get("key") or "",
            "title": f.get("summary") or "",
            "status": status,
            "opened": (f.get("created") or "")[:10],
            "url": f"{_site(cfg['site'])}/browse/{it.get('key')}",
            "assignee": _user(f.get("assignee")),
            "reporter": _user(f.get("reporter")),
        })
    return {"key": key, "issues": issues}


def build_bundle(fetched, g):
    email_idx, name_idx = {}, {}
    for pid, email, pname in db.read("MATCH (p:Person) RETURN p.id, p.email, p.name", None, g):
        if email:
            email_idx[str(email).lower()] = pid
        if pname:
            name_idx[str(pname).lower()] = pid
    known = set(email_idx) | set(name_idx)
    tickets = {str(k): tid for tid, k in db.read("MATCH (t:Ticket) WHERE t.key IS NOT NULL RETURN t.id, t.key", None, g)}
    systems = [(sid, sname) for sid, sname in db.read("MATCH (s:System) RETURN s.id, s.name", None, g)]
    aliases = {sname: names.system_aliases(sname) for _, sname in systems}
    name_to_id = {sname: sid for sid, sname in systems}

    nodes, links, link_keys = {}, [], set()
    added_people, linked_people, ticket_count = [], set(), 0

    def node(label, nid, name, **props):
        nodes.setdefault((label, nid), {"label": label, "id": nid, "props": {"name": name, "source": "jira", **props}})

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
        pid = "jira-" + slugify(u["account_id"] or u["name"] or "user")
        node("Person", pid, u["name"] or u["email"] or pid, email=u["email"], jira=u["account_id"])
        if u["email"]:
            email_idx[u["email"]] = pid
        if u["name"]:
            name_idx[u["name"].lower()] = pid
        added_people.append(u["name"] or u["email"] or pid)
        return pid

    def system_in(title):
        hits = names.find_in_text(title, aliases)
        return name_to_id[hits[0]] if len(hits) == 1 else None

    for proj in fetched:
        for it in proj["issues"]:
            if not it["key"]:
                continue
            tid = tickets.get(it["key"]) or f"jira-{slugify(it['key'])}"
            tickets[it["key"]] = tid
            node("Ticket", tid, it["key"], key=it["key"], title=it["title"], status=it["status"],
                 opened=it["opened"], url=it["url"])
            t = ("Ticket", tid)
            who = person(it["assignee"])
            if who:
                link(t, "ASSIGNS", ("Person", who))
            who = person(it["reporter"])
            if who:
                link(("Person", who), "AUTHORED", t)
            sid = system_in(it["title"])
            if sid:
                link(t, "ABOUT", ("System", sid))
            ticket_count += 1
    return ({"nodes": list(nodes.values()), "links": links},
            {"tickets": ticket_count, "people_linked": len(linked_people), "people_added": added_people})


def sync(cfg, g, selected=None):
    keys = project_keys(selected if selected is not None else cfg.get("projects", []))
    limit = cfg.get("issue_limit") if cfg.get("issue_limit") in ISSUE_LIMITS else DEFAULT_ISSUE_LIMIT
    if not keys:
        raise JiraError("Pick at least one project to sync.")
    creds = creds_for(cfg)
    fetched, errors = [], []
    for key in keys:
        try:
            fetched.append(fetch_project(creds, key, limit))
        except JiraError as err:
            errors.append(f"{key}: {err}")
    if not fetched:
        raise JiraError(errors[0] if errors else "Nothing to sync.")
    bundle, stats = build_bundle(fetched, g)
    assert not any(l["rel"] in ("OWNS", "PROPOSES") for l in bundle["links"])
    totals = loader.load_bundle(bundle, g)
    return {"at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "projects": len(fetched), "tickets": stats["tickets"], "people_linked": stats["people_linked"],
            "people_added": stats["people_added"], "nodes": totals["nodes"], "links": totals["links"],
            "errors": errors}
