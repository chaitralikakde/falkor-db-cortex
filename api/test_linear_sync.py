"""Offline test of the Linear sync against a mock Linear GraphQL API.

    docker compose exec api python test_linear_sync.py
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import db
import linear_sync
import loader

G = "lineartest"


def issue(key, title, status, assignee, creator):
    def user(name, email, uid):
        return {"id": uid, "name": name, "email": email}
    return {"identifier": key, "title": title, "url": f"https://linear.app/lumen/issue/{key}",
            "createdAt": "2026-10-01T09:00:00.000Z", "state": {"name": status},
            "assignee": user(*assignee) if assignee else None,
            "creator": user(*creator) if creator else None}


LUM = [issue("LUM-12", "Payments API keeps timing out on invoices", "Done",
             ("Priya Shah", "priya@lumen.example", "lin-priya"),
             ("Noah Kim", "noah@lumen.example", "lin-noah")),
       issue("LUM-88", "New hire laptop", "Todo",
             ("New Hire", "join@lumen.example", "lin-new"),
             ("Maya Chen", "maya@lumen.example", "lin-maya"))]
MKT = [issue("MKT-1", "Pricing on the Marketing site", "Done",
             ("Riley Cho", "riley@lumen.example", "lin-riley"),
             ("Riley Cho", "riley@lumen.example", "lin-riley"))]


class Mock(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def reply(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def do_POST(self):
        auth = self.headers.get("Authorization") or ""
        if auth != "Bearer lin_good":
            return self.reply(401, {"errors": [{"message": "Authentication required"}]})
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        payload = json.loads(raw) if raw else {}
        q = payload.get("query") or ""
        v = payload.get("variables") or {}
        if "viewer" in q:
            return self.reply(200, {"data": {"viewer": {"id": "usr-maya", "name": "Maya Chen",
                                                         "email": "maya@lumen.example"}}})
        if "teams(" in q:
            return self.reply(200, {"data": {"teams": {"nodes": [
                {"id": "team-lum", "key": "LUM", "name": "Lumen"},
                {"id": "team-mkt", "key": "MKT", "name": "Marketing"}]}}})
        if "team(" in q:
            tid = v.get("id")
            if tid == "GONE":
                return self.reply(200, {"data": {"team": None}})
            nodes = MKT if tid == "team-mkt" else LUM
            return self.reply(200, {"data": {"team": {"issues": {"nodes": nodes}}}})
        return self.reply(400, {"errors": [{"message": "unknown query"}]})


def count(cypher, params=None):
    return db.read(cypher, params, G)[0][0]


def main():
    linear_sync.API = "http://127.0.0.1:8769/graphql"
    srv = HTTPServer(("127.0.0.1", 8769), Mock)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    cfg = {"token": "lin_good"}

    try:
        linear_sync.verify("")
        raise AssertionError("blank token must fail")
    except linear_sync.LinearError:
        pass
    info = linear_sync.verify("lin_good")
    assert info["name"] == "Maya Chen", info
    teams = linear_sync.list_teams("lin_good")
    assert [t["id"] for t in teams] == ["team-lum", "team-mkt"], teams

    try:
        db.graph(G).delete()
    except Exception:
        pass
    loader.load_seed(G)
    owns_before = count("MATCH ()-[o:OWNS]->() RETURN count(o)")
    proposes_before = count("MATCH ()-[p:PROPOSES]->() RETURN count(p)")
    tickets_before = count("MATCH (t:Ticket) RETURN count(t)")
    people_before = count("MATCH (p:Person) RETURN count(p)")

    out = linear_sync.sync({**cfg, "teams": ["team-lum", "team-mkt", "GONE"], "issue_limit": 20}, G)
    assert out["teams"] == 2 and out["tickets"] == 3, out
    assert out["errors"] and "GONE" in out["errors"][0]
    assert "New Hire" in out["people_added"]

    assert count("MATCH (t:Ticket {key: 'LUM-12'}) RETURN count(t)") == 1
    assert count("MATCH (:Ticket {key: 'LUM-12'})-[:ABOUT]->(:System {name: 'Payments API'}) RETURN count(*)") == 1
    assert count("MATCH (:Ticket {key: 'LUM-12'})-[:ASSIGNS]->(:Person {id: 'priya'}) RETURN count(*)") == 1
    assert count("MATCH (:Person {id: 'noah'})-[:AUTHORED]->(:Ticket {key: 'LUM-12'}) RETURN count(*)") == 1
    assert count("MATCH (t:Ticket {key: 'LUM-88'}) RETURN count(t)") == 1
    assert count("MATCH (:Ticket {key: 'MKT-1'})-[:ABOUT]->(:System {name: 'Marketing site'}) RETURN count(*)") == 1
    assert count("MATCH (p:Person) RETURN count(p)") == people_before + 1
    assert count("MATCH ()-[o:OWNS]->() RETURN count(o)") == owns_before
    assert count("MATCH ()-[p:PROPOSES]->() RETURN count(p)") == proposes_before
    assert count("MATCH (t:Ticket) RETURN count(t)") == tickets_before + 2

    nodes = count("MATCH (n) RETURN count(n)")
    linear_sync.sync({**cfg, "teams": ["team-lum", "team-mkt"], "issue_limit": 20}, G)
    assert count("MATCH (n) RETURN count(n)") == nodes

    try:
        linear_sync.sync({**cfg, "teams": []}, G)
        raise AssertionError("empty selection must fail")
    except linear_sync.LinearError:
        pass
    db.graph(G).delete()
    print("ok: verify, teams, reuse LUM-12, match people, ABOUT from title, no OWNS, idempotent")


if __name__ == "__main__":
    main()
