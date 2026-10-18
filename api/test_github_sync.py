"""Offline test of the GitHub sync against a mock GitHub API. Uses a scratch graph, not `lumen`.

    docker compose exec api python test_github_sync.py
"""
import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

import db
import github_sync
import loader

G = "ghtest"


def pr(number, title, user, merged=None, state="closed", created="2026-10-10T09:00:00Z"):
    return {"number": number, "title": title, "state": state, "merged_at": merged, "created_at": created,
            "html_url": f"https://github.com/lumen-hq/lumen-api/pull/{number}", "user": {"login": user, "type": "User"}}


ROUTES = {
    "/user": {"login": "maya-chen", "name": "Maya Chen"},
    "/user/repos": [
        {"full_name": "lumen-hq/lumen-api", "name": "lumen-api", "owner": {"login": "lumen-hq"}, "private": True,
         "html_url": "https://github.com/lumen-hq/lumen-api", "language": "Python", "pushed_at": "2026-10-17T00:00:00Z"},
        {"full_name": "lumen-hq/new-repo", "name": "new-repo", "owner": {"login": "lumen-hq"}, "private": False,
         "html_url": "https://github.com/lumen-hq/new-repo", "language": "Go", "pushed_at": "2026-10-01T00:00:00Z"},
    ],
    "/repos/lumen-hq/lumen-api": {"full_name": "lumen-hq/lumen-api", "name": "lumen-api", "private": True,
                                  "html_url": "https://github.com/lumen-hq/lumen-api", "language": "Python",
                                  "description": "Backend"},
    "/repos/lumen-hq/new-repo": {"full_name": "lumen-hq/new-repo", "name": "new-repo", "private": False,
                                 "html_url": "https://github.com/lumen-hq/new-repo", "language": "Go"},
    "/repos/lumen-hq/lumen-api/pulls": [
        pr(41, "Stop the invoice charge timeout", "priya-shah", merged="2026-04-02T10:00:00Z"),  # already in the seed
        pr(60, "Add rate limiting", "priya-shah", state="open"),
        {**pr(61, "Bump deps", "dependabot[bot]", state="open"), "user": {"login": "dependabot[bot]", "type": "Bot"}},
    ],
    "/repos/lumen-hq/new-repo/pulls": [pr(1, "First commit", "newcomer", merged="2026-10-02T10:00:00Z")],
    "/repos/lumen-hq/lumen-api/pulls/41/reviews": [{"user": {"login": "diego-alvarez", "type": "User"}}],
    "/repos/lumen-hq/lumen-api/pulls/60/reviews": [
        {"user": {"login": "someone-new", "type": "User"}}, {"user": {"login": "someone-new", "type": "User"}},
        {"user": {"login": "priya-shah", "type": "User"}},                        # the author reviewing herself
        {"user": {"login": "dependabot[bot]", "type": "Bot"}}],
    "/repos/lumen-hq/lumen-api/pulls/61/reviews": [],
    "/repos/lumen-hq/new-repo/pulls/1/reviews": [],
}
AUTH = []


class Mock(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        path = urllib.parse.urlsplit(self.path).path
        AUTH.append(self.headers.get("Authorization"))
        if self.headers.get("Authorization") != "Bearer ghp_good":
            return self.reply(401, {"message": "Bad credentials"})
        if path not in ROUTES:
            return self.reply(404, {"message": "Not Found"})
        self.reply(200, ROUTES[path], {"X-OAuth-Scopes": "repo, read:org"} if path == "/user" else {})

    def reply(self, code, body, headers=None):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())


def count(cypher, params=None):
    return db.read(cypher, params, G)[0][0]


def main():
    srv = HTTPServer(("127.0.0.1", 8767), Mock)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    github_sync.API = "http://127.0.0.1:8767"

    try:
        github_sync.verify("ghp_bad")
        raise AssertionError("a bad token must be rejected")
    except github_sync.GitHubError as err:
        assert "rejected the token" in str(err), err
    info = github_sync.verify("ghp_good")
    assert info == {"login": "maya-chen", "name": "Maya Chen", "scopes": ["repo", "read:org"]}, info
    repos = github_sync.list_repos("ghp_good")
    assert [r["full_name"] for r in repos] == ["lumen-hq/lumen-api", "lumen-hq/new-repo"] and repos[0]["private"]

    try:
        db.graph(G).delete()
    except Exception:
        pass
    loader.load_seed(G)
    owns_before = count("MATCH ()-[o:OWNS]->() RETURN count(o)")
    proposes_before = count("MATCH ()-[o:PROPOSES]->() RETURN count(o)")
    prs_before = count("MATCH (p:PullRequest) RETURN count(p)")
    persons_before = count("MATCH (p:Person) RETURN count(p)")

    cfg = {"token": "ghp_good", "repos": ["lumen-hq/lumen-api", "lumen-hq/new-repo", "lumen-hq/gone"], "pr_limit": 20}
    out = github_sync.sync(cfg, G)
    assert out["repos"] == 2 and out["prs"] == 4, out
    assert out["errors"] and "lumen-hq/gone" in out["errors"][0], "a missing repo is reported, the rest still sync"
    assert sorted(out["people_added"]) == ["newcomer", "someone-new"], out["people_added"]
    assert out["people_linked"] == 2, out        # priya-shah and diego-alvarez already in the graph

    # the seed's PR 41 is reused, not duplicated; the new PR joins the existing repo
    assert count("MATCH (p:PullRequest {number: 41}) RETURN count(p)") == 1
    assert count("MATCH (p:PullRequest {id: 'pr-lumen-hq-lumen-api-60'})-[:PART_OF]->(r:Repo {id: 'repo-api'}) RETURN count(p)") == 1
    assert count("MATCH (p:PullRequest) RETURN count(p)") == prs_before + 3     # 60, 61, new-repo #1
    # authors and reviewers match existing people by GitHub login
    assert count("MATCH (:Person {id: 'priya'})-[:AUTHORED]->(:PullRequest {number: 60}) RETURN count(*)") == 1
    assert count("MATCH (:Person {id: 'diego'})-[:REVIEWED]->(:PullRequest {id: 'pr-41'}) RETURN count(*)") == 1
    assert count("MATCH (p:Person {id: 'gh-priya-shah'}) RETURN count(p)") == 0, "priya must not be duplicated"
    assert count("MATCH (:Person {id: 'priya'})-[:REVIEWED]->(:PullRequest {number: 60}) RETURN count(*)") == 0, "no self review"
    assert count("MATCH (p:Person) WHERE p.github CONTAINS 'bot' RETURN count(p)") == 0, "bots are skipped"
    assert count("MATCH (p:Person) RETURN count(p)") == persons_before + 2
    # several systems share lumen-api, so a PR is not guessed to change any of them
    assert count("MATCH (:PullRequest {number: 60})-[:CHANGES]->() RETURN count(*)") == 0
    # the rule that matters: GitHub never creates ownership
    assert count("MATCH ()-[o:OWNS]->() RETURN count(o)") == owns_before
    assert count("MATCH ()-[o:PROPOSES]->() RETURN count(o)") == proposes_before

    # running it again changes nothing
    nodes = count("MATCH (n) RETURN count(n)")
    edges = count("MATCH ()-[r]->() RETURN count(r)")
    github_sync.sync(cfg, G)
    assert count("MATCH (n) RETURN count(n)") == nodes and count("MATCH ()-[r]->() RETURN count(r)") == edges

    try:
        github_sync.sync({"token": "ghp_good", "repos": []}, G)
        raise AssertionError("an empty selection must be refused")
    except github_sync.GitHubError:
        pass
    db.graph(G).delete()
    print("ok: verify, repo list, reuse of seed PRs and people, bots skipped, no OWNS, idempotent, partial failure")


if __name__ == "__main__":
    main()
