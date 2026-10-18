"""Offline test of the Notion sync against a mock Notion API.

    docker compose exec api python test_notion_sync.py
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import db
import loader
import notion_sync

G = "notiontest"


def rich(text):
    return [{"plain_text": text}]


def page(pid, title, author, created="2026-10-01T09:00:00.000Z"):
    def user(name, email, uid):
        return {"object": "user", "id": uid, "name": name, "type": "person", "person": {"email": email}}
    return {"object": "page", "id": pid, "url": f"https://www.notion.so/{pid}",
            "created_time": created, "created_by": user(*author) if author else {"type": "bot"},
            "properties": {"Name": {"type": "title", "title": rich(title)}}}


class Mock(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def reply(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def do_GET(self):
        if (self.headers.get("Authorization") or "") != "Bearer ntn_good":
            return self.reply(401, {"message": "Unauthorized"})
        if self.path == "/users/me":
            return self.reply(200, {"id": "bot-1", "name": "Graph Desk", "type": "bot",
                                    "bot": {"workspace_name": "Lumen"}})
        return self.reply(404, {"message": "Not Found"})

    def do_POST(self):
        if (self.headers.get("Authorization") or "") != "Bearer ntn_good":
            return self.reply(401, {"message": "Unauthorized"})
        if self.path == "/search":
            return self.reply(200, {"has_more": False, "results": [
                {"object": "database", "id": "db-eng", "title": rich("Engineering docs"),
                 "url": "https://www.notion.so/db-eng"},
                {"object": "database", "id": "db-mkt", "title": rich("Marketing docs"),
                 "url": "https://www.notion.so/db-mkt"}]})
        if self.path == "/databases/gone-db/query":
            return self.reply(404, {"message": "Could not find database"})
        if self.path == "/databases/db-mkt/query":
            return self.reply(200, {"results": [
                page("pg-mkt", "Pricing on the Marketing site",
                     ("Riley Cho", "riley@lumen.example", "u-riley"))]})
        if self.path == "/databases/db-eng/query":
            return self.reply(200, {"results": [
                page("pg-adr", "ADR-12: Payments uses Postgres",
                     ("Priya Shah", "priya@lumen.example", "u-priya")),
                page("pg-new", "Payments API on-call",
                     ("New Writer", "write@lumen.example", "u-new"))]})
        return self.reply(404, {"message": "Not Found"})


def count(cypher, params=None):
    return db.read(cypher, params, G)[0][0]


def main():
    notion_sync.API = "http://127.0.0.1:8770"
    srv = HTTPServer(("127.0.0.1", 8770), Mock)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    cfg = {"token": "ntn_good"}

    try:
        notion_sync.verify("")
        raise AssertionError("blank token must fail")
    except notion_sync.NotionError:
        pass
    info = notion_sync.verify("ntn_good")
    assert info["name"] == "Graph Desk" and info["workspace"] == "Lumen", info
    dbs = notion_sync.list_databases("ntn_good")
    assert [d["id"] for d in dbs] == ["db-eng", "db-mkt"], dbs

    try:
        db.graph(G).delete()
    except Exception:
        pass
    loader.load_seed(G)
    owns_before = count("MATCH ()-[o:OWNS]->() RETURN count(o)")
    proposes_before = count("MATCH ()-[p:PROPOSES]->() RETURN count(p)")
    docs_before = count("MATCH (d:Doc) RETURN count(d)")
    people_before = count("MATCH (p:Person) RETURN count(p)")

    out = notion_sync.sync({**cfg, "databases": ["db-eng", "db-mkt", "gone-db"], "page_limit": 20}, G)
    assert out["databases"] == 2 and out["docs"] == 3, out
    assert out["errors"] and "gone-db" in out["errors"][0]
    assert "New Writer" in out["people_added"]

    assert count("MATCH (d:Doc {id: 'doc-12'}) RETURN count(d)") == 1
    assert count("MATCH (:Doc {id: 'doc-12'})-[:ABOUT]->(:System {name: 'Payments API'}) RETURN count(*)") == 1
    assert count("MATCH (:Person {id: 'priya'})-[:AUTHORED]->(:Doc {id: 'doc-12'}) RETURN count(*)") == 1
    assert count("MATCH (d:Doc {notion: 'pg-new'})-[:ABOUT]->(:System {name: 'Payments API'}) RETURN count(*)") == 1
    assert count("MATCH (:Doc {notion: 'pg-mkt'})-[:ABOUT]->(:System {name: 'Marketing site'}) RETURN count(*)") == 1
    assert count("MATCH (p:Person) RETURN count(p)") == people_before + 1
    assert count("MATCH ()-[o:OWNS]->() RETURN count(o)") == owns_before
    assert count("MATCH ()-[p:PROPOSES]->() RETURN count(p)") == proposes_before
    assert count("MATCH (d:Doc) RETURN count(d)") == docs_before + 2

    nodes = count("MATCH (n) RETURN count(n)")
    notion_sync.sync({**cfg, "databases": ["db-eng", "db-mkt"], "page_limit": 20}, G)
    assert count("MATCH (n) RETURN count(n)") == nodes

    try:
        notion_sync.sync({**cfg, "databases": []}, G)
        raise AssertionError("empty selection must fail")
    except notion_sync.NotionError:
        pass
    db.graph(G).delete()
    print("ok: verify, databases, reuse ADR-12, match people, ABOUT from title, no OWNS, idempotent")


if __name__ == "__main__":
    main()
