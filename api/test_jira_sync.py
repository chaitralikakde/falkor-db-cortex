"""Offline test of the Jira sync against a mock Jira API.

    docker compose exec api python test_jira_sync.py
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

import db
import jira_sync
import loader

G = "jiratest"
SITE = "http://127.0.0.1:8768"


def issue(key, summary, status, assignee, reporter, created="2026-10-01T09:00:00.000+0000"):
    def user(name, email, account):
        return {"accountId": account, "displayName": name, "emailAddress": email, "accountType": "atlassian"}
    return {"key": key, "fields": {
        "summary": summary, "status": {"name": status}, "created": created,
        "assignee": user(*assignee) if assignee else None,
        "reporter": user(*reporter)}}


ROUTES_GET = {
    "/rest/api/3/myself": {"accountId": "acc-maya", "displayName": "Maya Chen",
                           "emailAddress": "maya@lumen.example"},
    "/rest/api/3/project/search": {"total": 2, "values": [
        {"key": "LUM", "name": "Lumen", "projectTypeKey": "software"},
        {"key": "MKT", "name": "Marketing", "projectTypeKey": "business"}]},
    "/rest/api/3/search": {"issues": [
        issue("LUM-12", "Payments API keeps timing out on invoices", "Done",
              ("Priya Shah", "priya@lumen.example", "acc-priya"),
              ("Noah Kim", "noah@lumen.example", "acc-noah")),
        issue("LUM-99", "New hire laptop", "To Do",
              ("New Hire", "join@lumen.example", "acc-new"),
              ("Maya Chen", "maya@lumen.example", "acc-maya")),
    ]},
}


class Mock(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def _auth_ok(self):
        return (self.headers.get("Authorization") or "").startswith("Basic ")

    def reply(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def do_GET(self):
        if not self._auth_ok():
            return self.reply(401, {"message": "Unauthorized"})
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/rest/api/3/search":
            jql = (parse_qs(parsed.query).get("jql") or [""])[0]
            if "GONE" in jql:
                return self.reply(404, {"errorMessages": ["project not found"]})
            if "MKT" in jql:
                return self.reply(200, {"issues": [issue("MKT-1", "Pricing on the Marketing site", "Done",
                    ("Riley Cho", "riley@lumen.example", "acc-riley"),
                    ("Riley Cho", "riley@lumen.example", "acc-riley"))]})
        if path not in ROUTES_GET:
            return self.reply(404, {"message": "Not Found"})
        self.reply(200, ROUTES_GET[path])

    def do_POST(self):
        if not self._auth_ok():
            return self.reply(401, {"message": "Unauthorized"})
        path = urlparse(self.path).path
        if path != "/rest/api/3/search/jql":
            return self.reply(404, {"errorMessages": ["nope"]})
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        jql = (json.loads(raw) if raw else {}).get("jql", "")
        if "GONE" in jql:
            return self.reply(404, {"errorMessages": ["project not found"]})
        if "MKT" in jql:
            issues = [issue("MKT-1", "Pricing on the Marketing site", "Done",
                            ("Riley Cho", "riley@lumen.example", "acc-riley"),
                            ("Riley Cho", "riley@lumen.example", "acc-riley"))]
        else:
            issues = ROUTES_GET["/rest/api/3/search"]["issues"]
        self.reply(200, {"issues": issues})


def count(cypher, params=None):
    return db.read(cypher, params, G)[0][0]


def main():
    srv = HTTPServer(("127.0.0.1", 8768), Mock)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    cfg = {"site": SITE, "email": "maya@lumen.example", "token": "jira-good"}

    try:
        jira_sync.verify({**cfg, "token": ""})
        raise AssertionError("blank token must fail")
    except jira_sync.JiraError:
        pass
    info = jira_sync.verify(cfg)
    assert info["name"] == "Maya Chen" and info["site"] == SITE, info
    projects = jira_sync.list_projects(cfg)
    assert [p["key"] for p in projects] == ["LUM", "MKT"], projects

    try:
        db.graph(G).delete()
    except Exception:
        pass
    loader.load_seed(G)
    owns_before = count("MATCH ()-[o:OWNS]->() RETURN count(o)")
    proposes_before = count("MATCH ()-[p:PROPOSES]->() RETURN count(p)")
    tickets_before = count("MATCH (t:Ticket) RETURN count(t)")
    people_before = count("MATCH (p:Person) RETURN count(p)")

    out = jira_sync.sync({**cfg, "projects": ["LUM", "MKT", "GONE"], "issue_limit": 20}, G)
    assert out["projects"] == 2 and out["tickets"] == 3, out
    assert out["errors"] and "GONE" in out["errors"][0]
    assert "New Hire" in out["people_added"]

    # LUM-12 already in the seed is reused; ABOUT Payments API from the summary
    assert count("MATCH (t:Ticket {key: 'LUM-12'}) RETURN count(t)") == 1
    assert count("MATCH (:Ticket {key: 'LUM-12'})-[:ABOUT]->(:System {name: 'Payments API'}) RETURN count(*)") == 1
    assert count("MATCH (:Ticket {key: 'LUM-12'})-[:ASSIGNS]->(:Person {id: 'priya'}) RETURN count(*)") == 1
    assert count("MATCH (:Person {id: 'noah'})-[:AUTHORED]->(:Ticket {key: 'LUM-12'}) RETURN count(*)") == 1
    assert count("MATCH (t:Ticket {key: 'LUM-99'}) RETURN count(t)") == 1
    assert count("MATCH (t:Ticket {key: 'MKT-1'})-[:ABOUT]->(:System {name: 'Marketing site'}) RETURN count(*)") == 1
    assert count("MATCH (p:Person) RETURN count(p)") == people_before + 1
    assert count("MATCH ()-[o:OWNS]->() RETURN count(o)") == owns_before
    assert count("MATCH ()-[p:PROPOSES]->() RETURN count(p)") == proposes_before
    assert count("MATCH (t:Ticket) RETURN count(t)") == tickets_before + 2

    nodes = count("MATCH (n) RETURN count(n)")
    jira_sync.sync({**cfg, "projects": ["LUM", "MKT"], "issue_limit": 20}, G)
    assert count("MATCH (n) RETURN count(n)") == nodes

    try:
        jira_sync.sync({**cfg, "projects": []}, G)
        raise AssertionError("empty selection must fail")
    except jira_sync.JiraError:
        pass
    db.graph(G).delete()
    print("ok: verify, projects, reuse LUM-12, match people, ABOUT from title, no OWNS, idempotent")


if __name__ == "__main__":
    main()
