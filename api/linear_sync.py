"""Linear connector: read teams and issues with a personal API key.

Plain HTTPS GraphQL, no SDK. A sync writes Ticket nodes, links the assignee and creator
(matched by email, display name, or Person.linear), and may link ABOUT a System when the
title names exactly one known system. It never writes OWNS or PROPOSES. Re-running a sync
is a MERGE on the ticket key.
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

API = os.environ.get("LINEAR_API", "https://api.linear.app/graphql")
MAX_TEAMS = 25
ISSUE_LIMITS = (10, 20, 50)
DEFAULT_ISSUE_LIMIT = 20
TEAM_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

VIEWER = "query { viewer { id name email } }"
TEAMS = "query { teams(first: 50) { nodes { id key name } } }"
ISSUES = """
query($id: String!, $n: Int!) {
  team(id: $id) {
    issues(first: $n, orderBy: updatedAt) {
      nodes {
        identifier title url createdAt
        state { name }
        assignee { id name email }
        creator { id name email }
      }
    }
  }
}
"""


class LinearError(Exception):
    def __init__(self, message, status=0):
        super().__init__(message)
        self.status = status


def env_token():
    return (os.environ.get("LINEAR_API_KEY") or os.environ.get("LINEAR_TOKEN") or "").strip()


def token_for(cfg):
    return ((cfg or {}).get("token") or "").strip() or env_token()


def team_ids(raw):
    out = []
    for k in raw or []:
        k = (k or "").strip()
        if TEAM_ID.match(k) and k not in out:
            out.append(k)
        if len(out) >= MAX_TEAMS:
            break
    return out


def graphql(token, query, variables=None):
    token = (token or "").strip()
    if not token:
        raise LinearError("Paste a Linear personal API key from linear.app → Settings → Security → Personal API keys.")
    auth = token if token.lower().startswith("bearer ") else f"Bearer {token}"
    req = urllib.request.Request(API, data=json.dumps({"query": query, "variables": variables or {}}).encode(),
                                 method="POST", headers={"Authorization": auth, "Content-Type": "application/json",
                                                         "User-Agent": "graph-desk/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=25) as res:
            body = json.loads(res.read().decode("utf-8", errors="replace") or "{}")
    except urllib.error.HTTPError as err:
        raise LinearError(_explain(err), err.code) from err
    except (urllib.error.URLError, TimeoutError) as err:
        raise LinearError(f"Could not reach Linear: {getattr(err, 'reason', err)}") from err
    if body.get("errors"):
        msg = (body["errors"][0] or {}).get("message") or "Linear returned an error."
        raise LinearError(msg)
    return body.get("data") or {}


def _explain(err):
    try:
        detail = json.loads(err.read().decode("utf-8", errors="replace"))
        msg = ((detail.get("errors") or [{}])[0].get("message") if isinstance(detail, dict) else "") or ""
    except (ValueError, OSError):
        msg = ""
    if err.code in (401, 403):
        return "Linear rejected the key. Create a personal API key and copy it in full."
    return f"Linear said {err.code}: {msg}".strip()


def verify(token):
    me = (graphql(token, VIEWER).get("viewer") or {})
    if not me.get("id"):
        raise LinearError("Linear did not return a user for that key.")
    return {"id": me.get("id", ""), "name": me.get("name") or "", "email": me.get("email") or ""}


def list_teams(token):
    nodes = ((graphql(token, TEAMS).get("teams") or {}).get("nodes") or [])
    return [{"id": t["id"], "key": t.get("key") or "", "name": t.get("name") or t.get("key") or t["id"],
             "url": f"https://linear.app/team/{t.get('key') or t['id']}"} for t in nodes if t.get("id")]


def _user(u):
    if not u:
        return None
    return {"id": u.get("id") or "", "name": u.get("name") or "", "email": (u.get("email") or "").lower()}


def fetch_team(token, team_id, limit):
    if not TEAM_ID.match(team_id or ""):
        raise LinearError(f"{team_id}: not a team id.")
    data = graphql(token, ISSUES, {"id": team_id, "n": min(limit, 50)})
    team = data.get("team")
    if not team:
        raise LinearError("Linear could not find that team, or this key cannot see it.")
    issues = []
    for it in (team.get("issues") or {}).get("nodes") or []:
        issues.append({
            "key": it.get("identifier") or "",
            "title": it.get("title") or "",
            "status": ((it.get("state") or {}).get("name") or "").lower(),
            "opened": (it.get("createdAt") or "")[:10],
            "url": it.get("url") or "",
            "assignee": _user(it.get("assignee")),
            "creator": _user(it.get("creator")),
        })
        if len(issues) >= limit:
            break
    return {"id": team_id, "issues": issues}


def build_bundle(fetched, g):
    email_idx, name_idx, linear_idx = {}, {}, {}
    for pid, email, pname, lin in db.read(
            "MATCH (p:Person) RETURN p.id, p.email, p.name, p.linear", None, g):
        if email:
            email_idx[str(email).lower()] = pid
        if pname:
            name_idx[str(pname).lower()] = pid
        if lin:
            linear_idx[str(lin).lower()] = pid
    known = set(email_idx) | set(name_idx) | set(linear_idx)
    tickets = {str(k): tid for tid, k in db.read(
        "MATCH (t:Ticket) WHERE t.key IS NOT NULL RETURN t.id, t.key", None, g)}
    systems = [(sid, sname) for sid, sname in db.read("MATCH (s:System) RETURN s.id, s.name", None, g)]
    aliases = {sname: names.system_aliases(sname) for _, sname in systems}
    name_to_id = {sname: sid for sid, sname in systems}

    nodes, links, link_keys = {}, [], set()
    added_people, linked_people, ticket_count = [], set(), 0

    def node(label, nid, name, **props):
        nodes.setdefault((label, nid), {"label": label, "id": nid, "props": {"name": name, "source": "linear", **props}})

    def link(src, rel, dst, **props):
        key = (src, rel, dst)
        if key not in link_keys:
            link_keys.add(key)
            links.append({"src": list(src), "rel": rel, "dst": list(dst), "props": props})

    def person(u):
        if not u:
            return None
        pid = ((email_idx.get(u["email"]) if u["email"] else None)
               or name_idx.get(u["name"].lower())
               or linear_idx.get(u["name"].lower())
               or linear_idx.get(u["id"].lower()))
        if pid:
            if (u["email"] in known) or (u["name"].lower() in known) or (u["id"].lower() in known):
                linked_people.add(pid)
            return pid
        pid = "lin-" + slugify(u["id"] or u["name"] or "user")
        node("Person", pid, u["name"] or u["email"] or pid, email=u["email"], linear=u["id"] or u["name"])
        if u["email"]:
            email_idx[u["email"]] = pid
        if u["name"]:
            name_idx[u["name"].lower()] = pid
        added_people.append(u["name"] or u["email"] or pid)
        return pid

    def system_in(title):
        hits = names.find_in_text(title, aliases)
        return name_to_id[hits[0]] if len(hits) == 1 else None

    for team in fetched:
        for it in team["issues"]:
            if not it["key"]:
                continue
            tid = tickets.get(it["key"]) or f"lin-{slugify(it['key'])}"
            tickets[it["key"]] = tid
            node("Ticket", tid, it["key"], key=it["key"], title=it["title"], status=it["status"],
                 opened=it["opened"], url=it["url"])
            t = ("Ticket", tid)
            who = person(it["assignee"])
            if who:
                link(t, "ASSIGNS", ("Person", who))
            who = person(it["creator"])
            if who:
                link(("Person", who), "AUTHORED", t)
            sid = system_in(it["title"])
            if sid:
                link(t, "ABOUT", ("System", sid))
            ticket_count += 1
    return ({"nodes": list(nodes.values()), "links": links},
            {"tickets": ticket_count, "people_linked": len(linked_people), "people_added": added_people})


def sync(cfg, g, selected=None):
    keys = team_ids(selected if selected is not None else cfg.get("teams", []))
    limit = cfg.get("issue_limit") if cfg.get("issue_limit") in ISSUE_LIMITS else DEFAULT_ISSUE_LIMIT
    if not keys:
        raise LinearError("Pick at least one team to sync.")
    token = token_for(cfg)
    fetched, errors = [], []
    for key in keys:
        try:
            fetched.append(fetch_team(token, key, limit))
        except LinearError as err:
            errors.append(f"{key}: {err}")
    if not fetched:
        raise LinearError(errors[0] if errors else "Nothing to sync.")
    bundle, stats = build_bundle(fetched, g)
    assert not any(l["rel"] in ("OWNS", "PROPOSES") for l in bundle["links"])
    totals = loader.load_bundle(bundle, g)
    return {"at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "teams": len(fetched), "tickets": stats["tickets"], "people_linked": stats["people_linked"],
            "people_added": stats["people_added"], "nodes": totals["nodes"], "links": totals["links"],
            "errors": errors}
