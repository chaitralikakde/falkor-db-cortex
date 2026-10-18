"""Offline test of the Slack bot against a mock Slack server. No Slack account needed.

    docker compose exec api python test_slack_bot.py

It asks real questions, so it writes Session nodes into the `lumen` graph. Reset the demo after:
    python -m load_seed --reset
"""
import json
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

import slack_bot

T0 = time.time()
BOT = "UBOT1"
MSGS = {
    "C1": [
        {"ts": f"{T0 + 1:.6f}", "user": "U111", "text": "lunch anyone?"},
        {"ts": f"{T0 + 1.5:.6f}", "user": "U111", "text": "who owns Auth?"},
        {"ts": f"{T0 + 2:.6f}", "user": "U111", "text": f"<@{BOT}> who owns Payments API?"},
        {"ts": f"{T0 + 3:.6f}", "bot_id": "B9", "text": f"<@{BOT}> another bot, ignore"},
        {"ts": f"{T0 + 4:.6f}", "user": "U222", "text": f"<@{BOT}> who owns the moon base?"},
        {"ts": f"{T0 + 4.5:.6f}", "user": "U222", "text": f"<@{BOT}> who owns it?"},
    ],
    "D1": [{"ts": f"{T0 + 5:.6f}", "user": "U333", "text": "why did we decide Payments API?"}],
    "C2": [],
}
JOINED = []
NAMES = {"U111": "Maya Chen", "U222": "Noah Kim", "U333": "Sam Okonkwo"}
POSTS, CALLS = [], []


class Mock(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        method = self.path.rsplit("/", 1)[-1]
        form = dict(urllib.parse.parse_qsl(self.rfile.read(int(self.headers["Content-Length"])).decode()))
        CALLS.append(method)
        out, headers = {"ok": True}, {}
        if method == "auth.test":
            out |= {"team": "Lumen HQ", "user": "graphdesk", "user_id": BOT}
            headers["x-oauth-scopes"] = "chat:write,channels:read,channels:history,im:history"
        elif method == "users.conversations":
            out["channels"] = [{"id": "C1", "name": "eng"}, {"id": "D1", "is_im": True, "user": "U333"}]
            out["channels"] += [{"id": c, "name": "design"} for c in JOINED]
        elif method == "conversations.list":
            out["channels"] = [{"id": "C1", "name": "eng", "is_member": True, "num_members": 9},
                               {"id": "C2", "name": "design", "is_member": bool(JOINED), "num_members": 4}]
        elif method == "conversations.join":
            JOINED.append(form["channel"])
        elif method == "conversations.history":
            old = float(form.get("oldest", 0))
            out["messages"] = [m for m in MSGS[form["channel"]] if float(m["ts"]) > old][::-1]
        elif method == "users.info":
            out["user"] = {"name": form["user"].lower(), "real_name": NAMES[form["user"]]}
        elif method == "chat.postMessage":
            POSTS.append(form)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        for k, v in headers.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(json.dumps(out).encode())


def main():
    srv = HTTPServer(("127.0.0.1", 8766), Mock)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    slack_bot.API = "http://127.0.0.1:8766"

    info = slack_bot.verify("xoxb-test")
    assert info["bot_id"] == BOT, info

    bot = slack_bot.Bot("lumen", {"bot_token": "xoxb-test", "off": [], **info})
    assert bot._types() == "public_channel", "no groups:read or im:read, so only public channels are listed"
    bot.started = T0
    bot.start()
    time.sleep(10)
    bot.stop()

    by = {p["channel"]: [] for p in POSTS}
    for p in POSTS:
        by[p["channel"]].append(p)

    assert len(by.get("C1", [])) == 4, f"expected 4 channel replies, got {len(by.get('C1', []))}"
    auth, owner, moon, pron = by["C1"]
    assert "Diego Alvarez owns Auth" in auth["text"], auth
    assert "Priya Shah owns Payments API" in owner["text"] and owner["thread_ts"], owner
    assert "<https://" in owner["text"], "sources should be Slack links"
    assert moon["text"].strip() == "I can't find a source.", moon["text"]
    assert pron["text"].strip() == "I can't find a source.", "'it' must not borrow another question's system"
    assert len(by.get("D1", [])) == 1 and "thread_ts" not in by["D1"][0], "DM reply is top-level"
    assert "Postgres" in by["D1"][0]["text"]
    assert CALLS.count("chat.postMessage") == 5, "each message answered exactly once"
    assert bot.error is None, bot.error
    # dashboard actions: list workspace channels, join one, switch one off and on
    ws = bot.workspace_channels()
    assert [(c["name"], c["member"]) for c in ws] == [("design", False), ("eng", True)], ws
    rows, warn = bot.all_channels()
    assert warn is None and [(r["name"], r["kind"], r["member"]) for r in rows] == [
        ("eng", "public", True), ("design", "public", False), ("U333", "dm", True)], rows
    bot.join("C2")
    assert any(c["id"] == "C2" and c["listening"] for c in bot.channel_list()), bot.channel_list()
    rows, _ = bot.all_channels()
    assert next(r for r in rows if r["id"] == "C2")["member"], rows
    # settings: no thread, no sources, capped sources
    assert bot.opts == {"thread": True, "sources": True, "max_sources": 6}
    result = {"sentence": "Priya owns it.", "sources": [{"name": "a", "kind": "Doc"}, {"name": "b", "kind": "Doc"}]}
    assert "*Sources*" not in slack_bot.format_reply(result, False, 6)
    assert "+1 more" in slack_bot.format_reply(result, True, 1)
    bot.set_listening("C1", False)
    assert bot.cfg["off"] == ["C1"] and not next(c for c in bot.channel_list() if c["id"] == "C1")["listening"]
    bot.set_listening("C1", True)
    assert bot.cfg["off"] == [] and "C1" in bot.cursor

    # two department bots in the same channel: each only answers for its systems
    import loader
    loader.load_seed("lumen")
    POSTS.clear()
    eng = slack_bot.Bot("lumen", {"bot_token": "xoxb-test", "off": [], "department": "engineering", **info})
    eng.channels["C1"] = {"name": "eng", "im": False, "private": False}
    eng.handle_message("C1", {"ts": f"{T0 + 20:.6f}", "user": "U111",
                              "text": f"<@{BOT}> who owns Design system?"})
    assert POSTS[-1]["text"].strip() == "I can't find a source.", POSTS[-1]["text"]
    des = slack_bot.Bot("lumen", {"bot_token": "xoxb-test", "off": [], "department": "design",
                                 "bot_id": "UDES", "bot_user": "design", "team": "Lumen HQ"})
    des.channels["C1"] = {"name": "eng", "im": False, "private": False}
    des.handle_message("C1", {"ts": f"{T0 + 21:.6f}", "user": "U111",
                              "text": "<@UDES> who owns Design system?"})
    assert "Aisha Rahman owns Design system" in POSTS[-1]["text"], POSTS[-1]["text"]
    # tagging the other bot in the same message is ignored by this one
    n = len(POSTS)
    des.handle_message("C1", {"ts": f"{T0 + 22:.6f}", "user": "U111",
                              "text": f"<@{BOT}> who owns Payments API?"})
    assert len(POSTS) == n, "Design bot must ignore a mention of the Engineering bot"

    print("ok: mention in thread, refusal for unknown system, no pronoun borrowing, DM, no duplicates, bot ignored")


if __name__ == "__main__":
    main()
