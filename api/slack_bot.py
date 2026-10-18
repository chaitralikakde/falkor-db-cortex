"""Slack bot: tag it in a channel (or DM it) and it answers from the company graph.

Plain HTTPS to Slack's Web API with one bot token (xoxb-). No SDK, no public URL, no second token.
Every few seconds a worker lists the channels the bot was invited to, reads new messages with
`conversations.history`, and answers questions there — an @mention, an @botname, or a plain
who/why/what question in a channel the bot is listening in — plus any DM. Answers go through
the same `agents.ask` pipeline as the web Ask page. So an answer is still a path the graph
returned, and "no path" still means "I can't find a source."

Limits of polling: a reply lands a few seconds after the mention, and a mention inside an
existing thread is not seen (history only lists top-level messages). Slack's Events API
removes both limits once the app has a public URL; `Bot.handle_message` is what it would call.
"""
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import agents
import companies
import state

API = os.environ.get("SLACK_API_BASE", "https://slack.com/api")

# Scopes the bot needs. The first group is required, the rest are optional (private channels, DMs).
REQUIRED_SCOPES = ["chat:write", "channels:read", "channels:history"]
OPTIONAL_SCOPES = ["channels:join", "groups:read", "groups:history", "im:read", "im:history", "im:write", "users:read"]

# Paste into "Create New App → From a manifest" and every scope is set in one step.
MANIFEST = {
    "display_information": {
        "name": "Cortex",
        "description": "Ask who owns what and why we decided it. Answers come only from the company graph.",
        "background_color": "#0b0f14",
    },
    "features": {
        "bot_user": {"display_name": "Cortex", "always_online": True},
        "app_home": {"home_tab_enabled": False, "messages_tab_enabled": True,
                     "messages_tab_read_only_enabled": False},
    },
    "oauth_config": {"scopes": {"bot": REQUIRED_SCOPES + OPTIONAL_SCOPES + ["users:read.email"]}},
    "settings": {"org_deploy_enabled": False, "socket_mode_enabled": False, "token_rotation_enabled": False},
}

MAX_SOURCES = 6
# per-bot settings the dashboard can change; stored under cfg["settings"]
DEFAULT_SETTINGS = {"thread": True, "sources": True, "max_sources": MAX_SOURCES}
_bots = {}      # (company id, slack bot user id) -> Bot
_lock = threading.Lock()


class SlackError(Exception):
    def __init__(self, code, retry_after=0):
        super().__init__(code)
        self.code = code
        self.retry_after = retry_after


def call(token, method, **params):
    """One Slack Web API call. Returns (json, response headers). Raises SlackError."""
    data = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}).encode()
    req = urllib.request.Request(
        f"{API}/{method}", data=data, method="POST",
        headers={"Authorization": f"Bearer {token}", "User-Agent": "graph-desk/0.1",
                 "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=20) as res:
            body, headers = json.loads(res.read().decode("utf-8", errors="replace")), res.headers
    except urllib.error.HTTPError as err:
        if err.code == 429:
            raise SlackError("ratelimited", int(err.headers.get("Retry-After", "30"))) from err
        raise SlackError(f"http_{err.code}") from err
    except (urllib.error.URLError, TimeoutError) as err:
        raise SlackError(f"network: {getattr(err, 'reason', err)}") from err
    if not body.get("ok"):
        raise SlackError(body.get("error", "unknown_error"))
    return body, headers


class SlackSetupError(Exception):
    pass


def verify(bot_token):
    """Check the token with Slack before saving. Returns {team, bot_user, bot_id}."""
    if not bot_token.startswith("xoxb-"):
        raise SlackSetupError("A bot token starts with xoxb-. Find it under OAuth & Permissions, "
                              "after installing the app to your workspace.")
    try:
        auth, headers = call(bot_token, "auth.test")
    except SlackError as err:
        if err.code in ("invalid_auth", "not_authed", "token_revoked", "account_inactive"):
            raise SlackSetupError(f"Slack rejected the token ({err.code}). Copy it again from OAuth & Permissions.") from err
        raise SlackSetupError(f"Could not check the token with Slack: {err.code}") from err
    granted = {s.strip() for s in (headers.get("x-oauth-scopes") or "").split(",") if s.strip()}
    missing = [s for s in REQUIRED_SCOPES if s not in granted]
    if granted and missing:
        raise SlackSetupError(f"The bot is missing scopes: {', '.join(missing)}. Add them under OAuth & Permissions "
                              "→ Bot Token Scopes, then Reinstall to Workspace and copy the new token.")
    return {"team": auth.get("team", ""), "bot_user": auth.get("user", ""), "bot_id": auth.get("user_id", ""),
            "scopes": sorted(granted)}


# ------------------------------------------------------------ formatting --
def _mrkdwn(text):
    """Escape the three characters Slack treats as markup."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def format_reply(result, show_sources=True, max_sources=MAX_SOURCES):
    """Slack message text for an `agents.ask` result."""
    lines = [_mrkdwn(l) for l in result["sentence"].split("\n") if l.strip()]
    if lines and not result.get("refused"):
        lines[0] = f"*{lines[0]}*"
    src = []
    sources = result.get("sources", []) if show_sources else []
    for s in sources[:max_sources]:
        label = _mrkdwn(s["name"])
        url = s.get("url") or ""
        if url.startswith(("http://", "https://")):
            label = f"<{url}|{label}>"
        meta = s["kind"] + (f", {s['date']}" if s.get("date") else "")
        src.append(f"• {label} _({meta})_")
    if len(sources) > max_sources:
        src.append(f"_+{len(sources) - max_sources} more on the Graph page_")
    if src:
        lines += ["", "*Sources*"] + src
    return "\n".join(lines)


def clean_question(text, bot_id, bot_name=""):
    """Drop the @mention of the bot and Slack's link markup."""
    text = re.sub(rf"<@{re.escape(bot_id)}(\|[^>]*)?>", "", text or "")
    text = re.sub(r"<@([A-Z0-9]+)(\|[^>]*)?>", r"\1", text)
    if bot_name:
        text = re.sub(rf"(?i)@{re.escape(bot_name)}\b", "", text)
    text = re.sub(r"<#[A-Z0-9]+\|([^>]*)>", r"#\1", text)
    text = re.sub(r"<(https?://[^|>]+)\|([^>]*)>", r"\2", text)
    text = re.sub(r"<(https?://[^>]+)>", r"\1", text)
    return text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").strip()


def looks_like_ask(text):
    """A channel message that is a question even without tagging the bot."""
    t = (text or "").strip()
    if re.search(r"(?i)\b(who|why|what|which|where|how)\b", t):
        return True
    if re.search(r"(?i)\b(owns?|owner|decid)", t):
        return True
    return "?" in t and len(t.split()) >= 3


# ------------------------------------------------------------------- bot --
class Bot:
    REFRESH = 30        # seconds between "which channels am I in?" lookups
    MIN_POLL = 3        # seconds between rounds
    PER_CALL = 1.5      # seconds of budget per channel, keeps us under Slack's rate limit

    def __init__(self, company_id, cfg):
        self.company_id = company_id
        self.cfg = cfg                       # the stored dict; `off` is saved through it
        self.token = cfg["bot_token"]
        self.bot_id = cfg.get("bot_id", "")
        self.off = set(cfg.get("off", []))   # channel ids the admin switched off
        self.scopes = set(cfg.get("scopes", []))
        self.last_refresh = 0
        self.error = None
        self.channels = {}                   # id -> {"name", "im", "private"}
        self.cursor = {}                     # channel id -> last handled ts
        self.names = {}                      # slack user id -> display name
        self.started = time.time()
        self.refreshed = False
        self.stop_flag = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True, name=f"slack-{company_id}")
        self.answered = 0

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_flag.set()

    @property
    def running(self):
        return self.thread.is_alive() and not self.stop_flag.is_set()

    # -- polling loop --
    def _run(self):
        while not self.stop_flag.is_set():
            wait = self.MIN_POLL
            try:
                if time.time() - self.last_refresh > self.REFRESH:
                    self._refresh_channels()
                active = [c for c in self.channels if c not in self.off]
                for cid in active:
                    if self.stop_flag.is_set():
                        return
                    self._poll(cid)
                wait = max(self.MIN_POLL, len(active) * self.PER_CALL)
                self.error = None
            except SlackError as err:
                self.error = err.code
                wait = max(wait, err.retry_after or 10)
                if err.code in ("invalid_auth", "token_revoked", "account_inactive"):
                    self.error = "Slack no longer accepts this token. Reconnect with a new one."
                    return
            except Exception as err:  # keep the worker alive
                self.error = f"{type(err).__name__}: {err}"
                print(f"slack[{self.company_id}] {self.error}")
            self.stop_flag.wait(wait)

    @property
    def opts(self):
        return {**DEFAULT_SETTINGS, **self.cfg.get("settings", {})}

    def _types(self):
        """Conversation types this token may list. Asking for one it has no scope for fails the whole call."""
        if not self.scopes:
            return "public_channel"
        want = [("public_channel", "channels:read"), ("private_channel", "groups:read"), ("im", "im:read")]
        return ",".join(t for t, s in want if s in self.scopes) or "public_channel"

    def _refresh_channels(self):
        found, cursor = {}, None
        while True:
            body, _ = call(self.token, "users.conversations", types=self._types(),
                           exclude_archived="true", limit=200, cursor=cursor)
            for c in body.get("channels", []):
                found[c["id"]] = {"name": c.get("name") or c.get("user") or c["id"], "im": bool(c.get("is_im")),
                                  "private": bool(c.get("is_private"))}
            cursor = (body.get("response_metadata") or {}).get("next_cursor")
            if not cursor:
                break
        now = time.time()
        for cid in found:
            # first sight of a channel: pick up the last minute so a question asked while we
            # were restarting still gets a reply
            self.cursor.setdefault(cid, f"{now - 90:.6f}")
        self.channels, self.refreshed = found, True
        self.last_refresh = time.time()

    # -- what the dashboard manages --
    def set_listening(self, channel, on):
        """Switch answering on or off in one channel. Turning it on starts from now, so a
        message sent while it was off is never answered late."""
        if on:
            self.off.discard(channel)
            self.cursor[channel] = f"{time.time():.6f}"
        else:
            self.off.add(channel)
        self.cfg["off"] = sorted(self.off)
        state.save()

    def channel_list(self):
        rows = [{"id": cid, "name": c["name"], "im": c["im"], "private": c["private"], "listening": cid not in self.off}
                for cid, c in self.channels.items()]
        return sorted(rows, key=lambda r: (r["im"], r["name"].lower()))

    def workspace_channels(self):
        """Public channels in the workspace, with whether the bot is already in each."""
        out, cursor = [], None
        for _ in range(5):
            body, _ = call(self.token, "conversations.list", types="public_channel", exclude_archived="true",
                           limit=200, cursor=cursor)
            out += [{"id": c["id"], "name": c.get("name", c["id"]), "member": bool(c.get("is_member")),
                     "members": c.get("num_members", 0)} for c in body.get("channels", [])]
            cursor = (body.get("response_metadata") or {}).get("next_cursor")
            if not cursor:
                break
        return sorted(out, key=lambda r: r["name"].lower())

    def all_channels(self):
        """Every channel the dashboard should list: all public channels in the workspace, plus the
        private channels and DMs the bot is in. Returns (rows, warning)."""
        try:
            self._refresh_channels()
        except SlackError as err:
            return [], f"Slack said {err.code}"
        warning, rows, seen = None, [], set()
        try:
            for c in self.workspace_channels():
                member = c["member"] or c["id"] in self.channels
                seen.add(c["id"])
                rows.append({"id": c["id"], "name": c["name"], "kind": "public", "member": member,
                             "members": c["members"], "listening": member and c["id"] not in self.off})
        except SlackError as err:
            warning = f"Could not list every public channel ({err.code}). Showing only the channels the bot is in."
        for cid, c in self.channels.items():
            if cid in seen:
                continue
            kind = "dm" if c["im"] else "private" if c["private"] else "public"
            rows.append({"id": cid, "name": c["name"], "kind": kind, "member": True, "members": 0,
                         "listening": cid not in self.off})
        order = {"public": 0, "private": 1, "dm": 2}
        rows.sort(key=lambda r: (order[r["kind"]], not r["member"], r["name"].lower()))
        return rows, warning

    def leave(self, channel):
        call(self.token, "conversations.leave", channel=channel)
        self.channels.pop(channel, None)

    def join(self, channel):
        call(self.token, "conversations.join", channel=channel)
        self._refresh_channels()
        self.off.discard(channel)

    def _poll(self, channel):
        try:
            body, _ = call(self.token, "conversations.history", channel=channel,
                           oldest=self.cursor[channel], limit=30)
        except SlackError as err:
            if err.code in ("not_in_channel", "channel_not_found", "missing_scope"):
                self.channels.pop(channel, None)   # e.g. a private channel without groups:history
                self.error = f"cannot read {channel}: {err.code}"
                return
            raise
        for msg in sorted(body.get("messages", []), key=lambda m: float(m["ts"])):
            self.cursor[channel] = msg["ts"]
            try:
                self.handle_message(channel, msg)
            except SlackError as err:
                if err.code == "ratelimited":
                    raise
                self.error = f"reply failed: {err.code}"
            except Exception as err:
                self.error = f"{type(err).__name__}: {err}"
                print(f"slack[{self.company_id}] message failed: {self.error}")

    # -- answering --
    def _name(self, user_id):
        if user_id not in self.names:
            try:
                u = call(self.token, "users.info", user=user_id)[0]["user"]
                self.names[user_id] = (u.get("profile") or {}).get("display_name") or u.get("real_name") or u.get("name") or user_id
            except SlackError:
                self.names[user_id] = user_id
        return self.names[user_id]

    def _post(self, channel, thread_ts, text):
        call(self.token, "chat.postMessage", channel=channel, thread_ts=thread_ts, text=text,
             unfurl_links="false", unfurl_media="false")

    def _named(self, text):
        for n in (self.cfg.get("bot_user"), self.cfg.get("label")):
            if n and re.search(rf"(?i)@{re.escape(n)}\b", text or ""):
                return True
        return False

    def handle_message(self, channel, msg):
        """Answer a DM, an @mention, or a question in a channel this bot is listening in."""
        if msg.get("bot_id") or msg.get("subtype") or not msg.get("user") or msg.get("user") == self.bot_id:
            return
        text = msg.get("text") or ""
        is_dm = bool(self.channels.get(channel, {}).get("im")) or channel.startswith("D")
        tagged = re.findall(r"<@(U[A-Z0-9]+)", text)
        if tagged and self.bot_id not in tagged:
            return
        if not is_dm and self.bot_id not in tagged and not self._named(text) and not looks_like_ask(text):
            return
        question = clean_question(text, self.bot_id, self.cfg.get("bot_user") or self.cfg.get("label") or "")
        opts = self.opts
        thread = None if is_dm or not opts["thread"] else (msg.get("thread_ts") or msg["ts"])
        company = companies.get_company(self.company_id)
        if not company:
            return
        if not question:
            self._post(channel, thread, "Ask me who owns something or why we decided it, for example: "
                                        "_who owns Billing Service?_")
            return
        if not company["finished"]:
            self._post(channel, thread, "This company's graph isn't finished yet. An admin needs to finish setup first.")
            return
        settings = state.settings(self.company_id, company["name"])
        # no carried-over context here: in a shared channel "it" could mean anyone's earlier question
        result = agents.ask(company["graph"], question, settings, asked_by=self._name(msg["user"]),
                            use_context=False, department=self.cfg.get("department"))
        self._post(channel, thread, format_reply(result, opts["sources"], opts["max_sources"]))
        self.answered += 1


# ----------------------------------------------------------- lifecycle --
def start(company_id, cfg):
    stop(company_id, cfg["bot_id"])
    bot = Bot(company_id, cfg)
    bot.start()
    with _lock:
        _bots[(company_id, cfg["bot_id"])] = bot
    return bot


def get(company_id, bot_id):
    return _bots.get((company_id, bot_id))


def stop(company_id, bot_id):
    with _lock:
        bot = _bots.pop((company_id, bot_id), None)
    if bot:
        bot.stop()


def stop_all():
    with _lock:
        bots = list(_bots.values())
        _bots.clear()
    for bot in bots:
        bot.stop()


def view(company_id, cfg):
    """One bot as the dashboard sees it. Never the token, only a hint of its last four characters."""
    bot = get(company_id, cfg["bot_id"])
    return {
        "id": cfg["bot_id"],
        "label": cfg.get("label") or cfg.get("bot_user", ""),
        "team": cfg.get("team", ""),
        "bot_user": cfg.get("bot_user", ""),
        "bot_hint": state.hint(cfg.get("bot_token", "")),
        "department": cfg.get("department") or "",
        "settings": {**DEFAULT_SETTINGS, **cfg.get("settings", {})},
        "missing_scopes": [s for s in OPTIONAL_SCOPES if cfg.get("scopes") and s not in cfg["scopes"]],
        "running": bool(bot and bot.running),
        "error": bot.error if bot else None,
        "answered": bot.answered if bot else 0,
        "channels": bot.channel_list() if bot else [],
    }


def boot_all():
    """Restart every saved bot. Called once when the API starts."""
    for cid, cfg in state.all_slack():
        start(cid, cfg)
        print(f"slack[{cid}] {cfg.get('label') or cfg.get('bot_user', '?')} listening in {cfg.get('team', '?')}")
