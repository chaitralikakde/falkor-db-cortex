"""GitHub connector: read repositories and pull requests with a personal access token.

Plain HTTPS to the GitHub REST API, no SDK. A sync writes Repo and PullRequest nodes, links each
pull request to its repo, and links its author and reviewers (matched by GitHub login to a Person
already in the graph, or added as a new Person). It never writes OWNS or PROPOSES: a pull request
is evidence of who touched a system, not a decision about who owns it. Only the admin's Apply
creates an OWNS link.

Re-running a sync is safe: every write is a MERGE on a stable id.
"""
import datetime
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import json

import db
import loader
from companies import slugify

API = os.environ.get("GITHUB_API_BASE", "https://api.github.com")
MAX_REPOS = 25
PR_LIMITS = (10, 20, 50)
DEFAULT_PR_LIMIT = 20


class GitHubError(Exception):
    def __init__(self, message, status=0):
        super().__init__(message)
        self.status = status


def env_token():
    return (os.environ.get("GITHUB_TOKEN") or "").strip()


def token_for(cfg):
    """The token a stored config uses: the one pasted in the dashboard, else the server's."""
    return ((cfg or {}).get("token") or "").strip() or env_token()


def call(token, path, params=None, pages=1):
    """GET one GitHub API path (following `Link: rel=next` up to `pages`). Returns (json, headers)."""
    url = f"{API}{path}" + (("?" + urllib.parse.urlencode(params)) if params else "")
    out, headers = None, None
    for _ in range(max(1, pages)):
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "graph-desk/0.1"})
        try:
            with urllib.request.urlopen(req, timeout=20) as res:
                body, headers = json.loads(res.read().decode("utf-8", errors="replace")), res.headers
        except urllib.error.HTTPError as err:
            raise GitHubError(_explain(err), err.code) from err
        except (urllib.error.URLError, TimeoutError) as err:
            raise GitHubError(f"Could not reach GitHub: {getattr(err, 'reason', err)}") from err
        out = body if out is None else (out + body if isinstance(body, list) else body)
        m = re.search(r'<([^>]+)>;\s*rel="next"', headers.get("Link") or "")
        if not isinstance(body, list) or not m:
            break
        url = m.group(1)
    return out, headers


def _explain(err):
    try:
        detail = json.loads(err.read().decode("utf-8", errors="replace")).get("message", "")
    except (ValueError, OSError):
        detail = ""
    if err.code == 401:
        return "GitHub rejected the token. Check that it is copied in full and has not expired."
    if err.code == 403 and err.headers.get("x-ratelimit-remaining") == "0":
        return "GitHub's rate limit is used up for this token. Try again in a few minutes."
    if err.code == 403:
        return f"GitHub refused: {detail or 'the token lacks access'}."
    if err.code == 404:
        return "GitHub could not find that, or the token cannot see it."
    return f"GitHub said {err.code}: {detail}".strip()


def verify(token):
    """Check a token with GitHub. Returns {login, name, scopes}."""
    token = (token or "").strip()
    if not token:
        raise GitHubError("Paste a personal access token (it starts with ghp_ or github_pat_).")
    user, headers = call(token, "/user")
    scopes = [s.strip() for s in (headers.get("x-oauth-scopes") or "").split(",") if s.strip()]
    return {"login": user.get("login", ""), "name": user.get("name") or "", "scopes": scopes}


def list_repos(token):
    """Repositories the token can read, most recently pushed first."""
    rows, _ = call(token, "/user/repos", {"per_page": 100, "sort": "pushed",
                                          "affiliation": "owner,collaborator,organization_member"}, pages=5)
    return [{
        "full_name": r["full_name"], "name": r["name"], "owner": (r.get("owner") or {}).get("login", ""),
        "private": bool(r.get("private")), "archived": bool(r.get("archived")), "fork": bool(r.get("fork")),
        "description": r.get("description") or "", "language": r.get("language") or "",
        "pushed": (r.get("pushed_at") or "")[:10], "url": r.get("html_url", ""),
        "open_issues": r.get("open_issues_count", 0),
    } for r in rows]


def _is_bot(user):
    return not user or user.get("type") == "Bot" or (user.get("login") or "").endswith("[bot]")


def fetch_repo(token, full_name, limit):
    """Repo facts plus its latest pull requests, each with its reviewers."""
    repo, _ = call(token, f"/repos/{full_name}")
    pulls, _ = call(token, f"/repos/{full_name}/pulls",
                    {"state": "all", "sort": "updated", "direction": "desc", "per_page": min(limit, 100)})
    prs = []
    for p in pulls[:limit]:
        try:
            reviews, _ = call(token, f"/repos/{full_name}/pulls/{p['number']}/reviews", {"per_page": 100})
        except GitHubError:
            reviews = []
        author = None if _is_bot(p.get("user")) else p["user"]["login"]
        reviewers = []
        for rv in reviews:
            who = None if _is_bot(rv.get("user")) else rv["user"]["login"]
            if who and who != author and who not in reviewers:
                reviewers.append(who)
        merged = bool(p.get("merged_at"))
        prs.append({"number": p["number"], "title": p.get("title", ""), "url": p.get("html_url", ""),
                    "state": "merged" if merged else p.get("state", "open"),
                    "date": ((p.get("merged_at") or p.get("created_at") or "")[:10]),
                    "author": author, "reviewers": reviewers})
    return {"repo": repo, "prs": prs}


# ----------------------------------------------------------------- graph --
def build_bundle(fetched, g):
    """Turn fetched repos into a bundle. `g` is the company graph, used to reuse what is already there."""
    people = {}      # lowercased github login -> person id
    for pid, gh in db.read("MATCH (p:Person) RETURN p.id, p.github", None, g):
        if gh:
            people[str(gh).lower()] = pid
    known = set(people)
    repos_by_url, repos_by_name = {}, {}
    for rid, name, url in db.read("MATCH (r:Repo) RETURN r.id, r.name, r.url", None, g):
        if url:
            repos_by_url[str(url).lower()] = rid
        elif name:
            repos_by_name[str(name).lower()] = rid
    prs_by_key = {(rid, num): pid for pid, num, rid in
                  db.read("MATCH (pr:PullRequest)-[:PART_OF]->(r:Repo) RETURN pr.id, pr.number, r.id", None, g)}
    systems = {}
    for rid, sid in db.read("MATCH (s:System)-[:PART_OF]->(r:Repo) RETURN r.id, s.id", None, g):
        systems.setdefault(rid, []).append(sid)

    nodes, links, link_keys = {}, [], set()
    added_people, linked_people, pr_count = [], set(), 0

    def node(label, nid, name, **props):
        nodes.setdefault((label, nid), {"label": label, "id": nid, "props": {"name": name, "source": "github", **props}})

    def link(src, rel, dst, **props):
        key = (src, rel, dst)
        if key not in link_keys:
            link_keys.add(key)
            links.append({"src": list(src), "rel": rel, "dst": list(dst), "props": props})

    def person(login):
        pid = people.get(login.lower())
        if pid:
            if login.lower() in known:      # someone already in the graph, not added earlier in this sync
                linked_people.add(login.lower())
            return pid
        pid = f"gh-{slugify(login)}"
        node("Person", pid, login, github=login, url=f"https://github.com/{login}")
        people[login.lower()] = pid
        added_people.append(login)
        return pid

    for item in fetched:
        r = item["repo"]
        url = r.get("html_url", "")
        rid = repos_by_url.get(url.lower()) or repos_by_name.get(r["name"].lower()) or f"repo-{slugify(r['full_name'])}"
        node("Repo", rid, r["name"], url=url, description=r.get("description") or "", language=r.get("language") or "",
             private=bool(r.get("private")))
        only_system = systems.get(rid, [])
        for p in item["prs"]:
            pid = prs_by_key.get((rid, p["number"])) or f"pr-{slugify(r['full_name'])}-{p['number']}"
            node("PullRequest", pid, f"PR {p['number']}", number=p["number"], title=p["title"], state=p["state"],
                 date=p["date"], url=p["url"])
            pr = ("PullRequest", pid)
            link(pr, "PART_OF", ("Repo", rid))
            if len(only_system) == 1:      # with several systems in one repo we cannot tell which a PR changed
                link(pr, "CHANGES", ("System", only_system[0]))
            if p["author"]:
                link(("Person", person(p["author"])), "AUTHORED", pr)
            for who in p["reviewers"]:
                link(("Person", person(who)), "REVIEWED", pr)
            pr_count += 1
    return ({"nodes": list(nodes.values()), "links": links},
            {"prs": pr_count, "people_linked": len(linked_people), "people_added": added_people})


def sync(cfg, g, repo_names=None):
    """Run one sync for the repos in `cfg["repos"]`. Returns a summary the dashboard shows."""
    token = token_for(cfg)
    names = list(repo_names if repo_names is not None else cfg.get("repos", []))[:MAX_REPOS]
    limit = cfg.get("pr_limit") if cfg.get("pr_limit") in PR_LIMITS else DEFAULT_PR_LIMIT
    if not names:
        raise GitHubError("Pick at least one repository to sync.")
    fetched, errors = [], []
    for full in names:
        try:
            fetched.append(fetch_repo(token, full, limit))
        except GitHubError as err:
            errors.append(f"{full}: {err}")
    if not fetched:
        raise GitHubError(errors[0] if errors else "Nothing to sync.")
    bundle, stats = build_bundle(fetched, g)
    assert not any(l["rel"] in ("OWNS", "PROPOSES") for l in bundle["links"])
    totals = loader.load_bundle(bundle, g)
    return {"at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "repos": len(fetched), "prs": stats["prs"], "people_linked": stats["people_linked"],
            "people_added": stats["people_added"], "nodes": totals["nodes"], "links": totals["links"],
            "errors": errors}
