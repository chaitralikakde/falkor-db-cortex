"""Per-company settings and connector cards.

Kept in a JSON file on the API's data volume so a restart keeps them. The model API key
lives in that file too, and `public_settings` strips it before anything goes to the browser.
"""
import copy
import json
import os
import tempfile
import threading

import llm

SUPER_PROMPT = (
    "You answer for {company} using the company graph only.\n"
    "Name the person, the system, and the source file, ticket, or message.\n"
    "If the graph returns no path, say you cannot find a source.\n"
    "Do not guess an owner."
)

SKILLS = [
    {"name": "Who owns this", "on": True,
     "when": "the question asks who owns or who can fix a system",
     "steps": "Mapper: recall_session, find_owner, find_experts, write_finding. Clerk reads the finding and names sources."},
    {"name": "Why we decided this", "on": True,
     "when": "the question asks why a choice was made",
     "steps": "Mapper: find_decision including WORKS_ON and WRITTEN_IN. Clerk includes the replaced decision."},
    {"name": "Handoff", "on": True,
     "when": "a ticket or message proposes a new owner",
     "steps": "Clerk: propose_handoff and a Task. The admin Applies it."},
]

CONNECTORS = [
    {"id": "upload", "name": "Uploaded documents", "connected": True, "read": True, "write": False, "from_seed": False},
    {"id": "github", "name": "GitHub", "connected": True, "read": True, "write": False, "from_seed": True},
    {"id": "linear", "name": "Linear", "connected": True, "read": True, "write": False, "from_seed": True},
    {"id": "slack", "name": "Slack", "connected": True, "read": True, "write": False, "from_seed": True},
    {"id": "notion", "name": "Notion", "connected": False, "read": False, "write": False, "from_seed": False},
    {"id": "jira", "name": "Jira", "connected": False, "read": False, "write": False, "from_seed": False},
]

NO_MODEL = {"provider": "none", "model": "", "base_url": "", "api_key": ""}

_lock = threading.Lock()
_settings = {}
_connectors = {}


def _path():
    for d in (os.environ.get("DATA_DIR", "/data"), os.path.join(os.path.dirname(__file__), ".data")):
        try:
            os.makedirs(d, exist_ok=True)
            probe = os.path.join(d, ".w")
            open(probe, "w").close()
            os.remove(probe)
            return os.path.join(d, "state.json")
        except OSError:
            continue
    return os.path.join(tempfile.gettempdir(), "graphdesk-state.json")


PATH = _path()


def _load():
    try:
        with open(PATH, encoding="utf-8") as f:
            data = json.load(f)
        _settings.update(data.get("settings", {}))
        _connectors.update(data.get("connectors", {}))
    except (OSError, ValueError):
        return
    # early builds kept one Slack config per company under "slack"; it is now a list of bots
    for s in _settings.values():
        old = s.pop("slack", None)
        if old and not s.get("slack_bots"):
            s["slack_bots"] = [{**old, "label": old.get("team") or "Slack bot", "off": []}]


def save():
    with _lock:
        tmp = PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"settings": _settings, "connectors": _connectors}, f)
        os.replace(tmp, PATH)


_load()


def settings(company_id, company_name):
    if company_id not in _settings:
        _settings[company_id] = {
            "super_prompt": SUPER_PROMPT.format(company=company_name),
            "skills": copy.deepcopy(SKILLS),
            "model": dict(NO_MODEL),
        }
        save()
    s = _settings[company_id]
    s["model"] = {**NO_MODEL, **s.get("model", {})}
    return s


def connectors(company_id):
    if company_id not in _connectors:
        cards = copy.deepcopy(CONNECTORS)
        for c in cards:
            c["last_sync"] = "seed" if (company_id == "lumen" and c["from_seed"]) else None
            if company_id != "lumen" and c["from_seed"]:
                c["connected"], c["read"] = False, False
        _connectors[company_id] = cards
        save()
    return _connectors[company_id]


# --------------------------------------------------------------- slack --
def slack_bots(company_id):
    """Stored Slack bots for a company: [{bot_token, bot_id, bot_user, team, label, off}]."""
    return (_settings.get(company_id) or {}).get("slack_bots", [])


def all_slack():
    return [(cid, cfg) for cid, s in _settings.items() for cfg in s.get("slack_bots", [])]


def slack_bot_config(company_id, bot_id):
    return next((c for c in slack_bots(company_id) if c.get("bot_id") == bot_id), None)


def add_slack(company_id, company_name, cfg):
    """Add a bot, or replace the stored one with the same bot id (a re-pasted token)."""
    s = settings(company_id, company_name)
    bots = [c for c in s.get("slack_bots", []) if c.get("bot_id") != cfg["bot_id"]]
    s["slack_bots"] = bots + [{"off": [], **cfg}]
    save()
    return s["slack_bots"][-1]


def remove_slack(company_id, bot_id):
    s = _settings.get(company_id) or {}
    s["slack_bots"] = [c for c in s.get("slack_bots", []) if c.get("bot_id") != bot_id]
    save()


# --------------------------------------------------------------- model --
def _hint(key):
    return ("••••" + key[-4:]) if len(key) >= 8 else ("••••" if key else "")


hint = _hint


# -------------------------------------------------------------- github --
def github_config(company_id):
    """The stored GitHub connection for a company, or None. `token` is absent when it uses the server's."""
    return (_settings.get(company_id) or {}).get("github")


def set_github(company_id, company_name, cfg):
    s = settings(company_id, company_name)
    if cfg:
        s["github"] = cfg
    else:
        s.pop("github", None)
    save()


def jira_config(company_id):
    return (_settings.get(company_id) or {}).get("jira")


def set_jira(company_id, company_name, cfg):
    s = settings(company_id, company_name)
    if cfg:
        s["jira"] = cfg
    else:
        s.pop("jira", None)
    save()


def linear_config(company_id):
    return (_settings.get(company_id) or {}).get("linear")


def set_linear(company_id, company_name, cfg):
    s = settings(company_id, company_name)
    if cfg:
        s["linear"] = cfg
    else:
        s.pop("linear", None)
    save()


def notion_config(company_id):
    return (_settings.get(company_id) or {}).get("notion")


def set_notion(company_id, company_name, cfg):
    s = settings(company_id, company_name)
    if cfg:
        s["notion"] = cfg
    else:
        s.pop("notion", None)
    save()


def public_model(m):
    """What the browser may see. Never the key itself."""
    prov = llm.BY_ID.get(m.get("provider"))
    stored = m.get("api_key") or ""
    from_env = not stored and bool(os.environ.get("MODEL_API_KEY")) and prov is not None
    connected = prov is not None and (bool(stored) or from_env or bool(prov.get("no_key")))
    model = m.get("model") or (prov["default_model"] if prov else "")
    if not prov:
        label = "rule-based (no model connected)"
    else:
        label = f"{prov['name']} · {model}" if model else prov["name"]
    return {
        "provider": m.get("provider", "none"),
        "model": m.get("model", ""),
        "base_url": m.get("base_url", ""),
        "has_key": bool(stored) or from_env,
        "key_hint": _hint(stored) if stored else ("from server environment" if from_env else ""),
        "connected": connected,
        "label": label,
    }


def public_settings(s):
    out = {k: v for k, v in s.items() if k not in ("slack_bots", "github", "jira", "linear", "notion")}
    out["model"] = public_model(s["model"])
    return out


def set_model(company_id, company_name, body):
    """Apply a draft from the Model tab. A blank key keeps the stored one for the same provider."""
    s = settings(company_id, company_name)
    cur = s["model"]
    provider = body.get("provider") or "none"
    if provider not in llm.BY_ID:
        s["model"] = dict(NO_MODEL)
    else:
        key = (body.get("api_key") or "").strip()
        if not key and provider == cur.get("provider"):
            key = cur.get("api_key", "")
        s["model"] = {
            "provider": provider,
            "model": (body.get("model") or "").strip(),
            "base_url": (body.get("base_url") or "").strip(),
            "api_key": key,
        }
    save()
    return public_model(s["model"])


def model_config(company_id, company_name):
    """The full config for server-side calls, or None when no model is usable."""
    m = settings(company_id, company_name)["model"]
    try:
        llm.resolve(m)
    except llm.LLMError:
        return None
    return m


def draft_config(company_id, company_name, body):
    """Stored config overlaid with whatever the Model tab sent, for Test and model lists."""
    m = dict(settings(company_id, company_name)["model"])
    provider = body.get("provider") or m.get("provider")
    if provider != m.get("provider"):
        m = {**NO_MODEL, "provider": provider}
    m["provider"] = provider
    if body.get("api_key"):
        m["api_key"] = body["api_key"].strip()
    if body.get("base_url") is not None:
        m["base_url"] = body["base_url"].strip()
    if body.get("model"):
        m["model"] = body["model"].strip()
    return m
