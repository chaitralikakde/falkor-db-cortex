import os
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import agents
import companies
import db
import departments
import extract
import github_sync
import jira_sync
import linear_sync
import notion_sync
import graphio
import handoff
import llm
import loader
import slack_bot
import state
from companies import slugify


@asynccontextmanager
async def lifespan(_app):
    for attempt in range(20):
        try:
            companies.boot()
            break
        except Exception as err:  # FalkorDB may still be starting
            print(f"boot attempt {attempt + 1} failed: {err}")
            time.sleep(1.5)
    # reconnect Slack bots in the background so a slow Slack never delays startup
    threading.Thread(target=slack_bot.boot_all, daemon=True).start()
    yield
    slack_bot.stop_all()


app = FastAPI(title="Cortex API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def company_or_404(company_id):
    c = companies.get_company(company_id)
    if not c:
        raise HTTPException(404, "company not found")
    return c


@app.get("/health")
def health():
    db.merge_node("Person", "healthcheck", {"name": "healthcheck"}, db.META_GRAPH)
    rows = db.read("MATCH (p:Person {id: $id}) RETURN p.name", {"id": "healthcheck"}, db.META_GRAPH)
    db.write("MATCH (p:Person {id: $id}) DELETE p", {"id": "healthcheck"}, db.META_GRAPH)
    return {"falkordb": "ok", "rows": rows, "model_key": bool(os.environ.get("MODEL_API_KEY"))}


# ------------------------------------------------------------- companies --
class NewCompany(BaseModel):
    name: str


@app.get("/companies")
def list_companies():
    return companies.list_companies()


@app.post("/companies")
def create_company(body: NewCompany):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "company name is required")
    return companies.create_company(name)


@app.get("/companies/{cid}/stats")
def stats(cid: str):
    c = company_or_404(cid)
    g = c["graph"]
    counts = db.read("MATCH (n) RETURN labels(n)[0], count(n)", None, g)
    links = db.read("MATCH ()-[r]->() RETURN count(r)", None, g)
    return {
        "company": c,
        "nodes": {k: v for k, v in counts},
        "total_nodes": sum(v for _, v in counts),
        "total_links": links[0][0] if links else 0,
        "people": loader.person_count(g),
    }


@app.post("/companies/{cid}/finish")
def finish(cid: str):
    c = company_or_404(cid)
    if loader.person_count(c["graph"]) < 1:
        raise HTTPException(400, "Add at least one person before finishing.")
    companies.set_finished(cid, True)
    return companies.get_company(cid)


@app.post("/companies/{cid}/reset")
def reset(cid: str):
    """Rebuild the Lumen demo from the seed (used before a recording)."""
    c = company_or_404(cid)
    if cid != companies.LUMEN:
        raise HTTPException(400, "Only the Lumen demo can be reset to the seed.")
    out = loader.reset_graph(c["graph"])
    companies.set_finished(cid, True)
    return out


# ----------------------------------------------------------------- graph --
@app.get("/companies/{cid}/graph")
def get_graph(cid: str):
    c = company_or_404(cid)
    return graphio.export_graph(c["graph"])


@app.get("/companies/{cid}/nodes/{node_id}")
def node_detail(cid: str, node_id: str):
    c = company_or_404(cid)
    g = c["graph"]
    rows = db.read(
        """MATCH (n {id: $id})
           OPTIONAL MATCH (n)-[r]->(o)
           RETURN n, 'out', r, o""", {"id": node_id}, g)
    rows += db.read(
        """MATCH (n {id: $id})
           OPTIONAL MATCH (o)-[r]->(n)
           RETURN n, 'in', r, o""", {"id": node_id}, g)
    if not rows:
        raise HTTPException(404, "node not found")
    n = graphio.node_json(rows[0][0])
    links = []
    for _, direction, r, o in rows:
        if r is None or o is None:
            continue
        other = graphio.node_json(o)
        links.append({
            "direction": direction, "rel": r.relation, "props": dict(r.properties),
            "other": {"id": other["id"], "label": other["label"], "name": other["data"]["name"]},
            "source": n["id"] if direction == "out" else other["id"],
            "target": other["id"] if direction == "out" else n["id"],
        })
    return {"node": n, "links": links}


class Unlink(BaseModel):
    source: str
    rel: str
    target: str


@app.post("/companies/{cid}/unlink")
def unlink(cid: str, body: Unlink):
    """Fix a wrong link from the Graph page. The nodes stay."""
    c = company_or_404(cid)
    if body.rel not in db.RELS:
        raise HTTPException(400, "unknown relationship")
    db.write(
        f"""MATCH (a {{id: $s}})-[r:{body.rel}]->(b {{id: $t}})
            DELETE r""", {"s": body.source, "t": body.target}, c["graph"])
    return {"removed": True}


# ---------------------------------------------------------------- upload --
@app.post("/companies/{cid}/upload")
async def upload(cid: str, files: list[UploadFile] = File(...)):
    c = company_or_404(cid)
    g = c["graph"]
    model = state.model_config(cid, c["name"])
    results = []
    for f in sorted(files, key=lambda x: x.filename or ""):
        raw = await f.read()
        fname = f.filename or "upload.md"
        if not fname.lower().endswith((".md", ".markdown", ".txt", ".pdf")):
            results.append({"file": fname, "error": "Only .md, .txt and .pdf files are supported."})
            continue
        try:
            b = extract.extract(fname, raw, g, model)
        except ValueError as err:
            results.append({"file": fname, "error": str(err)})
            continue
        bundle = b.as_dict()
        started = time.perf_counter()
        loader.load_bundle(bundle, g)
        tasks = []
        for p in b.proposals:
            tid, _ = handoff.propose_handoff(g, p["system"], p["owner"], [("Doc", p["doc"])])
            tasks.append(tid)
        written = graphio.bundle_to_graph(bundle)
        results.append({
            "file": fname,
            "notes": b.notes,
            "nodes": written["nodes"],
            "links": written["links"],
            "tasks": tasks,
            "ms": round((time.perf_counter() - started) * 1000, 1),
        })
    return {"results": results}


class PersonForm(BaseModel):
    team: str = ""
    person: str
    role: str = ""
    system: str = ""
    owner: bool = False


@app.post("/companies/{cid}/form")
def form(cid: str, body: PersonForm):
    """The five-field form: team, person, role, system, owner."""
    c = company_or_404(cid)
    g = c["graph"]
    person = body.person.strip()
    if not person:
        raise HTTPException(400, "person is required")
    nodes, links, notes = [], [], []

    people = {n.lower(): i for i, n in entity_names(g, "Person")}
    pid = people.get(person.lower())
    props = {"name": person}
    if body.role.strip():
        props["role"] = body.role.strip()
    if pid is None:
        pid = slugify(person)
        props["source"] = "form"
    nodes.append({"label": "Person", "id": pid, "props": props})
    notes.append(f"Person: {person}")

    team = body.team.strip()
    if team:
        teams = {n.lower(): i for i, n in entity_names(g, "Team")}
        tid = teams.get(team.lower())
        if tid is None:
            tid = f"team-{slugify(team)}"
            nodes.append({"label": "Team", "id": tid, "props": {"name": team, "source": "form"}})
        links.append({"src": ["Person", pid], "rel": "MEMBER_OF", "dst": ["Team", tid], "props": {}})
        notes.append(f"Team: {team}")

    system = body.system.strip()
    if system:
        systems = {n.lower(): i for i, n in entity_names(g, "System")}
        sid = systems.get(system.lower())
        if sid is None:
            sid = f"sys-{slugify(system)}"
            nodes.append({"label": "System", "id": sid, "props": {"name": system, "source": "form"}})
        notes.append(f"System: {system}")
        if body.owner:
            # the admin form is authoritative: end any other current owner, then start this one
            db.write(
                """MATCH (old:Person)-[o:OWNS]->(s:System {id: $sid})
                   WHERE o.end IS NULL AND old.id <> $pid SET o.end = $today""",
                {"sid": sid, "pid": pid, "today": db.TODAY}, g)
            links.append({"src": ["Person", pid], "rel": "OWNS", "dst": ["System", sid],
                          "props": {"start": db.TODAY, "source": "form"}})
            notes.append(f"OWNS: {person} owns {system}")

    bundle = {"nodes": nodes, "links": links}
    loader.load_bundle(bundle, g)
    written = graphio.bundle_to_graph(bundle)
    return {"notes": notes, "nodes": written["nodes"], "links": written["links"]}


def entity_names(g, label):
    """[(id, name)]"""
    return [(r[0], r[1]) for r in db.read(f"MATCH (n:{label}) RETURN n.id, n.name", None, g)]


# ------------------------------------------------------------------- ask --
class Question(BaseModel):
    question: str


@app.post("/companies/{cid}/ask")
def ask(cid: str, body: Question):
    c = company_or_404(cid)
    if not c["finished"]:
        raise HTTPException(409, "Finish onboarding before asking questions.")
    q = body.question.strip()
    if not q:
        raise HTTPException(400, "question is required")
    s = state.settings(cid, c["name"])
    out = agents.ask(c["graph"], q, s)
    out["model"] = state.public_model(s["model"])["label"]
    return out


@app.get("/companies/{cid}/answers")
def answers(cid: str):
    c = company_or_404(cid)
    return agents.answers(c["graph"])


# ----------------------------------------------------------------- tasks --
@app.get("/companies/{cid}/tasks")
def tasks(cid: str):
    c = company_or_404(cid)
    return handoff.list_tasks(c["graph"])


@app.post("/companies/{cid}/tasks/{task_id}/apply")
def apply_task(cid: str, task_id: str):
    """Admin only (the Graph page button). Ends the old OWNS, starts the new one."""
    c = company_or_404(cid)
    try:
        return handoff.apply_handoff(c["graph"], task_id)
    except LookupError as err:
        raise HTTPException(404, str(err)) from err
    except ValueError as err:
        raise HTTPException(409, str(err)) from err


@app.get("/companies/{cid}/risks")
def risks(cid: str):
    """Systems with exactly one person who ever authored a change."""
    c = company_or_404(cid)
    rows = db.read(
        """MATCH (s:System)
           OPTIONAL MATCH (p:Person)-[:AUTHORED]->(:PullRequest)-[:CHANGES]->(s)
           WITH s, collect(DISTINCT p.name) AS authors
           WHERE size(authors) = 1
           RETURN s.name, authors""", None, c["graph"])
    return [{"system": r[0], "authors": r[1]} for r in rows]


# ------------------------------------------------------ settings / cards --
class SettingsPatch(BaseModel):
    super_prompt: str | None = None
    skills: list[dict] | None = None


@app.get("/companies/{cid}/settings")
def get_settings(cid: str):
    c = company_or_404(cid)
    return state.public_settings(state.settings(cid, c["name"]))


@app.put("/companies/{cid}/settings")
def put_settings(cid: str, body: SettingsPatch):
    c = company_or_404(cid)
    s = state.settings(cid, c["name"])
    if body.super_prompt is not None:
        s["super_prompt"] = body.super_prompt
    if body.skills is not None:
        s["skills"] = body.skills
    state.save()
    return state.public_settings(s)


# ----------------------------------------------------------------- model --
class ModelDraft(BaseModel):
    provider: str = "none"
    model: str = ""
    base_url: str = ""
    api_key: str = ""


@app.get("/llm/providers")
def llm_providers():
    return llm.PROVIDERS


@app.put("/companies/{cid}/model")
def put_model(cid: str, body: ModelDraft):
    """Save provider, model, base URL and (optionally) a new API key. A blank key keeps the old one."""
    c = company_or_404(cid)
    return state.set_model(cid, c["name"], body.model_dump())


@app.delete("/companies/{cid}/model")
def delete_model(cid: str):
    """Disconnect: back to the rule-based logic, and the stored key is erased."""
    c = company_or_404(cid)
    return state.set_model(cid, c["name"], {"provider": "none"})


@app.post("/companies/{cid}/model/models")
def model_models(cid: str, body: ModelDraft):
    """Models the key can use, so the tab can show a dropdown. Never fails the page."""
    c = company_or_404(cid)
    cfg = state.draft_config(cid, c["name"], body.model_dump())
    try:
        return {"models": llm.list_models(cfg), "error": None}
    except llm.LLMError as err:
        return {"models": [], "error": str(err)}


@app.post("/companies/{cid}/model/test")
def model_test(cid: str, body: ModelDraft):
    """One tiny call with the draft settings, before saving."""
    c = company_or_404(cid)
    cfg = state.draft_config(cid, c["name"], body.model_dump())
    try:
        return llm.test(cfg)
    except llm.LLMError as err:
        return {"ok": False, "message": str(err)}


# ----------------------------------------------------------------- slack --
class SlackToken(BaseModel):
    bot_token: str
    label: str = ""
    department: str = ""


class SlackBotSettings(BaseModel):
    thread: bool | None = None
    sources: bool | None = None
    max_sources: int | None = None


class SlackBotPatch(BaseModel):
    label: str | None = None
    department: str | None = None
    settings: SlackBotSettings | None = None


class SlackChannelPatch(BaseModel):
    listening: bool


def slack_view(cid):
    return {"bots": [slack_bot.view(cid, cfg) for cfg in state.slack_bots(cid)]}


def slack_bot_or_404(cid, bot_id):
    company_or_404(cid)
    cfg = state.slack_bot_config(cid, bot_id)
    bot = slack_bot.get(cid, bot_id)
    if not cfg or not bot:
        raise HTTPException(404, "slack bot not found")
    return cfg, bot


@app.get("/companies/{cid}/departments")
def get_departments(cid: str):
    """Engineering, Design, Sales & Marketing, each with the systems and people its bot may name."""
    c = company_or_404(cid)
    return departments.public(c["graph"])


@app.get("/slack/manifest")
def slack_manifest():
    """Paste into Slack's "Create New App → From a manifest" to set every scope and event at once."""
    return slack_bot.MANIFEST


@app.get("/companies/{cid}/slack")
def get_slack(cid: str):
    company_or_404(cid)
    return slack_view(cid)


@app.post("/companies/{cid}/slack/bots")
def add_slack_bot(cid: str, body: SlackToken):
    """Check a bot token with Slack, save it, and start answering mentions."""
    c = company_or_404(cid)
    bot_token = body.bot_token.strip()
    for other, cfg in state.all_slack():
        if cfg.get("bot_token") == bot_token and other != cid:
            raise HTTPException(409, f"That Slack bot is already connected to the company “{other}”.")
    try:
        info = slack_bot.verify(bot_token)
    except slack_bot.SlackSetupError as err:
        raise HTTPException(400, str(err)) from err
    label = body.label.strip() or info["bot_user"] or "Slack bot"
    old = state.slack_bot_config(cid, info["bot_id"])
    dept = departments.known(body.department) or (old or {}).get("department") or ""
    cfg = state.add_slack(cid, c["name"], {"bot_token": bot_token, "label": label, "department": dept,
                                           "off": (old or {}).get("off", []), **info})
    slack_bot.start(cid, cfg)
    return slack_view(cid)


@app.patch("/companies/{cid}/slack/bots/{bot_id}")
def patch_slack_bot(cid: str, bot_id: str, body: SlackBotPatch):
    cfg, _ = slack_bot_or_404(cid, bot_id)
    if body.label is not None and body.label.strip():
        cfg["label"] = body.label.strip()
    if body.department is not None:
        cfg["department"] = departments.known(body.department) or ""
    if body.settings:
        change = body.settings.model_dump(exclude_none=True)
        if "max_sources" in change:
            change["max_sources"] = max(1, min(10, change["max_sources"]))
        cfg["settings"] = {**cfg.get("settings", {}), **change}
    state.save()
    return slack_view(cid)


@app.delete("/companies/{cid}/slack/bots/{bot_id}")
def delete_slack_bot(cid: str, bot_id: str):
    company_or_404(cid)
    slack_bot.stop(cid, bot_id)
    state.remove_slack(cid, bot_id)
    return slack_view(cid)


@app.get("/companies/{cid}/slack/bots/{bot_id}/channels")
def slack_workspace_channels(cid: str, bot_id: str):
    """Every public channel in the workspace plus the private channels and DMs the bot is in."""
    _, bot = slack_bot_or_404(cid, bot_id)
    rows, warning = bot.all_channels()
    return {"channels": rows, "warning": warning}


@app.post("/companies/{cid}/slack/bots/{bot_id}/channels/{channel}/leave")
def leave_slack_channel(cid: str, bot_id: str, channel: str):
    _, bot = slack_bot_or_404(cid, bot_id)
    try:
        bot.leave(channel)
    except slack_bot.SlackError as err:
        raise HTTPException(400, f"Slack said: {err.code}. Remove the bot from the channel in Slack instead.") from err
    return slack_view(cid)


@app.post("/companies/{cid}/slack/bots/{bot_id}/channels/{channel}/join")
def join_slack_channel(cid: str, bot_id: str, channel: str):
    _, bot = slack_bot_or_404(cid, bot_id)
    try:
        bot.join(channel)
    except slack_bot.SlackError as err:
        if err.code == "missing_scope":
            raise HTTPException(400, "The bot needs the channels:join scope to join on its own. Add it under "
                                     "OAuth & Permissions and reinstall, or type /invite in the channel.") from err
        raise HTTPException(400, f"Slack said: {err.code}. Try /invite in the channel instead.") from err
    return slack_view(cid)


@app.patch("/companies/{cid}/slack/bots/{bot_id}/channels/{channel}")
def patch_slack_channel(cid: str, bot_id: str, channel: str, body: SlackChannelPatch):
    """Switch answering on or off in one channel the bot is in."""
    _, bot = slack_bot_or_404(cid, bot_id)
    bot.set_listening(channel, body.listening)
    return slack_view(cid)


# ---------------------------------------------------------------- github --
class GitHubConnect(BaseModel):
    token: str = ""
    use_env: bool = False


class GitHubPatch(BaseModel):
    repos: list[str] | None = None
    pr_limit: int | None = None


def github_view(cid):
    cfg = state.github_config(cid)
    env = github_sync.env_token()
    base = {"connected": False, "env_available": bool(env), "env_hint": state.hint(env),
            "pr_limits": list(github_sync.PR_LIMITS)}
    if not cfg:
        return {**base, "login": "", "name": "", "scopes": [], "source": "", "token_hint": "", "repos": [],
                "pr_limit": github_sync.DEFAULT_PR_LIMIT, "last_sync": None, "last_result": None, "token_missing": False}
    token = github_sync.token_for(cfg)
    return {**base, "connected": True, "login": cfg.get("login", ""), "name": cfg.get("name", ""),
            "scopes": cfg.get("scopes", []), "source": "stored" if cfg.get("token") else "server",
            "token_hint": state.hint(token), "repos": cfg.get("repos", []),
            "pr_limit": cfg.get("pr_limit", github_sync.DEFAULT_PR_LIMIT), "last_sync": cfg.get("last_sync"),
            "last_result": cfg.get("last_result"), "token_missing": not token}


def github_cfg_or_400(cid):
    company_or_404(cid)
    cfg = state.github_config(cid)
    if not cfg:
        raise HTTPException(400, "GitHub is not connected for this company.")
    if not github_sync.token_for(cfg):
        raise HTTPException(400, "The server's GitHub token is no longer set. Paste a token to reconnect.")
    return cfg


@app.get("/companies/{cid}/github")
def get_github(cid: str):
    company_or_404(cid)
    return github_view(cid)


@app.put("/companies/{cid}/github")
def put_github(cid: str, body: GitHubConnect):
    """Check a personal access token (pasted, or the one set on the server) and save the connection."""
    c = company_or_404(cid)
    token = body.token.strip()
    if not token and not body.use_env:
        raise HTTPException(400, "Paste a personal access token, or use the one set on the server.")
    if not token and not github_sync.env_token():
        raise HTTPException(400, "No GITHUB_TOKEN is set on the server.")
    try:
        info = github_sync.verify(token or github_sync.env_token())
    except github_sync.GitHubError as err:
        raise HTTPException(400, str(err)) from err
    old = state.github_config(cid) or {}
    default_repos = [r.strip() for r in os.environ.get("GITHUB_REPOSITORY", "").split(",") if "/" in r]
    cfg = {"login": info["login"], "name": info["name"], "scopes": info["scopes"],
           "repos": old.get("repos") or default_repos, "pr_limit": old.get("pr_limit", github_sync.DEFAULT_PR_LIMIT),
           "last_sync": old.get("last_sync"), "last_result": old.get("last_result")}
    if token:
        cfg["token"] = token
    state.set_github(cid, c["name"], cfg)
    return github_view(cid)


@app.patch("/companies/{cid}/github")
def patch_github(cid: str, body: GitHubPatch):
    cfg = github_cfg_or_400(cid)
    if body.repos is not None:
        cfg["repos"] = [r for r in dict.fromkeys(body.repos) if "/" in r][:github_sync.MAX_REPOS]
    if body.pr_limit in github_sync.PR_LIMITS:
        cfg["pr_limit"] = body.pr_limit
    state.save()
    return github_view(cid)


@app.delete("/companies/{cid}/github")
def delete_github(cid: str):
    c = company_or_404(cid)
    state.set_github(cid, c["name"], None)
    return github_view(cid)


@app.get("/companies/{cid}/github/repos")
def github_repos(cid: str):
    cfg = github_cfg_or_400(cid)
    try:
        repos = github_sync.list_repos(github_sync.token_for(cfg))
    except github_sync.GitHubError as err:
        raise HTTPException(400, str(err)) from err
    picked = set(cfg.get("repos", []))
    return [{**r, "selected": r["full_name"] in picked} for r in repos]


@app.post("/companies/{cid}/github/sync")
def github_sync_now(cid: str):
    """Read the chosen repositories now and write what they say into this company's graph."""
    c = company_or_404(cid)
    cfg = github_cfg_or_400(cid)
    try:
        result = github_sync.sync(cfg, c["graph"])
    except github_sync.GitHubError as err:
        raise HTTPException(400, str(err)) from err
    cfg["last_sync"], cfg["last_result"] = result["at"], result
    state.save()
    return github_view(cid)


# ----------------------------------------------------------------- jira --
class JiraConnect(BaseModel):
    site: str = ""
    email: str = ""
    token: str = ""
    use_env: bool = False


class JiraPatch(BaseModel):
    projects: list[str] | None = None
    issue_limit: int | None = None


def jira_view(cid):
    cfg = state.jira_config(cid)
    env = jira_sync.env_creds()
    base = {"connected": False, "env_available": bool(env), "env_hint": state.hint((env or {}).get("token", "")),
            "env_site": (env or {}).get("site", ""), "issue_limits": list(jira_sync.ISSUE_LIMITS)}
    if not cfg:
        return {**base, "site": "", "email": "", "name": "", "token_hint": "", "projects": [],
                "issue_limit": jira_sync.DEFAULT_ISSUE_LIMIT, "last_sync": None, "last_result": None,
                "token_missing": False}
    creds = jira_sync.creds_for(cfg)
    return {**base, "connected": True, "site": cfg.get("site") or creds["site"],
            "email": cfg.get("email") or creds["email"], "name": cfg.get("name", ""),
            "token_hint": state.hint(creds["token"]), "projects": cfg.get("projects", []),
            "issue_limit": cfg.get("issue_limit", jira_sync.DEFAULT_ISSUE_LIMIT),
            "last_sync": cfg.get("last_sync"), "last_result": cfg.get("last_result"),
            "token_missing": not creds["token"]}


def jira_cfg_or_400(cid):
    company_or_404(cid)
    cfg = state.jira_config(cid)
    if not cfg:
        raise HTTPException(400, "Jira is not connected for this company.")
    if not jira_sync.creds_for(cfg)["token"]:
        raise HTTPException(400, "The Jira token is no longer set. Paste a token to reconnect.")
    return cfg


@app.get("/companies/{cid}/jira")
def get_jira(cid: str):
    company_or_404(cid)
    return jira_view(cid)


@app.put("/companies/{cid}/jira")
def put_jira(cid: str, body: JiraConnect):
    c = company_or_404(cid)
    env = jira_sync.env_creds()
    store_token = False
    if body.use_env:
        if not env:
            raise HTTPException(400, "No JIRA_SITE, JIRA_EMAIL and JIRA_API_TOKEN on the server.")
        draft = env
    else:
        draft = {"site": body.site.strip(), "email": body.email.strip(), "token": body.token.strip()}
        if draft["token"]:
            store_token = True
        elif env and draft["site"] == env.get("site") and draft["email"] == env.get("email"):
            draft["token"] = env["token"]
    try:
        info = jira_sync.verify(draft)
    except jira_sync.JiraError as err:
        raise HTTPException(400, str(err)) from err
    old = state.jira_config(cid) or {}
    cfg = {"site": info["site"], "email": info["email"], "name": info["name"], "account_id": info["account_id"],
           "projects": old.get("projects") or [],
           "issue_limit": old.get("issue_limit", jira_sync.DEFAULT_ISSUE_LIMIT),
           "last_sync": old.get("last_sync"), "last_result": old.get("last_result")}
    if store_token:
        cfg["token"] = draft["token"]
    state.set_jira(cid, c["name"], cfg)
    return jira_view(cid)


@app.patch("/companies/{cid}/jira")
def patch_jira(cid: str, body: JiraPatch):
    cfg = jira_cfg_or_400(cid)
    if body.projects is not None:
        cfg["projects"] = jira_sync.project_keys(body.projects)
    if body.issue_limit in jira_sync.ISSUE_LIMITS:
        cfg["issue_limit"] = body.issue_limit
    state.save()
    return jira_view(cid)


@app.delete("/companies/{cid}/jira")
def delete_jira(cid: str):
    c = company_or_404(cid)
    state.set_jira(cid, c["name"], None)
    return jira_view(cid)


@app.get("/companies/{cid}/jira/projects")
def jira_projects(cid: str):
    cfg = jira_cfg_or_400(cid)
    try:
        rows = jira_sync.list_projects(jira_sync.creds_for(cfg))
    except jira_sync.JiraError as err:
        raise HTTPException(400, str(err)) from err
    picked = set(cfg.get("projects", []))
    return [{**p, "selected": p["key"] in picked} for p in rows]


@app.post("/companies/{cid}/jira/sync")
def jira_sync_now(cid: str):
    c = company_or_404(cid)
    cfg = jira_cfg_or_400(cid)
    try:
        result = jira_sync.sync(cfg, c["graph"])
    except jira_sync.JiraError as err:
        raise HTTPException(400, str(err)) from err
    cfg["last_sync"], cfg["last_result"] = result["at"], result
    state.save()
    return jira_view(cid)


# --------------------------------------------------------------- linear --
class LinearConnect(BaseModel):
    token: str = ""
    use_env: bool = False


class LinearPatch(BaseModel):
    teams: list[str] | None = None
    issue_limit: int | None = None


def linear_view(cid):
    cfg = state.linear_config(cid)
    env = linear_sync.env_token()
    base = {"connected": False, "env_available": bool(env), "env_hint": state.hint(env),
            "issue_limits": list(linear_sync.ISSUE_LIMITS)}
    if not cfg:
        return {**base, "name": "", "email": "", "token_hint": "", "teams": [],
                "issue_limit": linear_sync.DEFAULT_ISSUE_LIMIT, "last_sync": None, "last_result": None,
                "token_missing": False}
    token = linear_sync.token_for(cfg)
    return {**base, "connected": True, "name": cfg.get("name", ""), "email": cfg.get("email", ""),
            "token_hint": state.hint(token), "teams": cfg.get("teams", []),
            "issue_limit": cfg.get("issue_limit", linear_sync.DEFAULT_ISSUE_LIMIT),
            "last_sync": cfg.get("last_sync"), "last_result": cfg.get("last_result"),
            "token_missing": not token}


def linear_cfg_or_400(cid):
    company_or_404(cid)
    cfg = state.linear_config(cid)
    if not cfg:
        raise HTTPException(400, "Linear is not connected for this company.")
    if not linear_sync.token_for(cfg):
        raise HTTPException(400, "The Linear key is no longer set. Paste a key to reconnect.")
    return cfg


@app.get("/companies/{cid}/linear")
def get_linear(cid: str):
    company_or_404(cid)
    return linear_view(cid)


@app.put("/companies/{cid}/linear")
def put_linear(cid: str, body: LinearConnect):
    c = company_or_404(cid)
    token = body.token.strip()
    if not token and not body.use_env:
        raise HTTPException(400, "Paste a Linear API key, or use the one set on the server.")
    if not token and not linear_sync.env_token():
        raise HTTPException(400, "No LINEAR_API_KEY is set on the server.")
    try:
        info = linear_sync.verify(token or linear_sync.env_token())
    except linear_sync.LinearError as err:
        raise HTTPException(400, str(err)) from err
    old = state.linear_config(cid) or {}
    cfg = {"name": info["name"], "email": info["email"], "teams": old.get("teams") or [],
           "issue_limit": old.get("issue_limit", linear_sync.DEFAULT_ISSUE_LIMIT),
           "last_sync": old.get("last_sync"), "last_result": old.get("last_result")}
    if token:
        cfg["token"] = token
    state.set_linear(cid, c["name"], cfg)
    return linear_view(cid)


@app.patch("/companies/{cid}/linear")
def patch_linear(cid: str, body: LinearPatch):
    cfg = linear_cfg_or_400(cid)
    if body.teams is not None:
        cfg["teams"] = linear_sync.team_ids(body.teams)
    if body.issue_limit in linear_sync.ISSUE_LIMITS:
        cfg["issue_limit"] = body.issue_limit
    state.save()
    return linear_view(cid)


@app.delete("/companies/{cid}/linear")
def delete_linear(cid: str):
    c = company_or_404(cid)
    state.set_linear(cid, c["name"], None)
    return linear_view(cid)


@app.get("/companies/{cid}/linear/teams")
def linear_teams(cid: str):
    cfg = linear_cfg_or_400(cid)
    try:
        rows = linear_sync.list_teams(linear_sync.token_for(cfg))
    except linear_sync.LinearError as err:
        raise HTTPException(400, str(err)) from err
    picked = set(cfg.get("teams", []))
    return [{**t, "selected": t["id"] in picked} for t in rows]


@app.post("/companies/{cid}/linear/sync")
def linear_sync_now(cid: str):
    c = company_or_404(cid)
    cfg = linear_cfg_or_400(cid)
    try:
        result = linear_sync.sync(cfg, c["graph"])
    except linear_sync.LinearError as err:
        raise HTTPException(400, str(err)) from err
    cfg["last_sync"], cfg["last_result"] = result["at"], result
    state.save()
    return linear_view(cid)


# --------------------------------------------------------------- notion --
class NotionConnect(BaseModel):
    token: str = ""
    use_env: bool = False


class NotionPatch(BaseModel):
    databases: list[str] | None = None
    page_limit: int | None = None


def notion_view(cid):
    cfg = state.notion_config(cid)
    env = notion_sync.env_token()
    base = {"connected": False, "env_available": bool(env), "env_hint": state.hint(env),
            "page_limits": list(notion_sync.PAGE_LIMITS)}
    if not cfg:
        return {**base, "name": "", "workspace": "", "token_hint": "", "databases": [],
                "page_limit": notion_sync.DEFAULT_PAGE_LIMIT, "last_sync": None, "last_result": None,
                "token_missing": False}
    token = notion_sync.token_for(cfg)
    return {**base, "connected": True, "name": cfg.get("name", ""), "workspace": cfg.get("workspace", ""),
            "token_hint": state.hint(token), "databases": cfg.get("databases", []),
            "page_limit": cfg.get("page_limit", notion_sync.DEFAULT_PAGE_LIMIT),
            "last_sync": cfg.get("last_sync"), "last_result": cfg.get("last_result"),
            "token_missing": not token}


def notion_cfg_or_400(cid):
    company_or_404(cid)
    cfg = state.notion_config(cid)
    if not cfg:
        raise HTTPException(400, "Notion is not connected for this company.")
    if not notion_sync.token_for(cfg):
        raise HTTPException(400, "The Notion token is no longer set. Paste a token to reconnect.")
    return cfg


@app.get("/companies/{cid}/notion")
def get_notion(cid: str):
    company_or_404(cid)
    return notion_view(cid)


@app.put("/companies/{cid}/notion")
def put_notion(cid: str, body: NotionConnect):
    c = company_or_404(cid)
    token = body.token.strip()
    if not token and not body.use_env:
        raise HTTPException(400, "Paste a Notion token, or use the one set on the server.")
    if not token and not notion_sync.env_token():
        raise HTTPException(400, "No NOTION_TOKEN is set on the server.")
    try:
        info = notion_sync.verify(token or notion_sync.env_token())
    except notion_sync.NotionError as err:
        raise HTTPException(400, str(err)) from err
    old = state.notion_config(cid) or {}
    cfg = {"name": info["name"], "workspace": info["workspace"], "databases": old.get("databases") or [],
           "page_limit": old.get("page_limit", notion_sync.DEFAULT_PAGE_LIMIT),
           "last_sync": old.get("last_sync"), "last_result": old.get("last_result")}
    if token:
        cfg["token"] = token
    state.set_notion(cid, c["name"], cfg)
    return notion_view(cid)


@app.patch("/companies/{cid}/notion")
def patch_notion(cid: str, body: NotionPatch):
    cfg = notion_cfg_or_400(cid)
    if body.databases is not None:
        cfg["databases"] = notion_sync.database_ids(body.databases)
    if body.page_limit in notion_sync.PAGE_LIMITS:
        cfg["page_limit"] = body.page_limit
    state.save()
    return notion_view(cid)


@app.delete("/companies/{cid}/notion")
def delete_notion(cid: str):
    c = company_or_404(cid)
    state.set_notion(cid, c["name"], None)
    return notion_view(cid)


@app.get("/companies/{cid}/notion/databases")
def notion_databases(cid: str):
    cfg = notion_cfg_or_400(cid)
    try:
        rows = notion_sync.list_databases(notion_sync.token_for(cfg))
    except notion_sync.NotionError as err:
        raise HTTPException(400, str(err)) from err
    picked = set(cfg.get("databases", []))
    return [{**d, "selected": d["id"] in picked} for d in rows]


@app.post("/companies/{cid}/notion/sync")
def notion_sync_now(cid: str):
    c = company_or_404(cid)
    cfg = notion_cfg_or_400(cid)
    try:
        result = notion_sync.sync(cfg, c["graph"])
    except notion_sync.NotionError as err:
        raise HTTPException(400, str(err)) from err
    cfg["last_sync"], cfg["last_result"] = result["at"], result
    state.save()
    return notion_view(cid)


def jira_card(cid, card):
    cfg = state.jira_config(cid)
    detail = None
    if cfg:
        n = len(cfg.get("projects", []))
        detail = f"{cfg.get('email') or cfg.get('name') or 'Jira'}, {n} project{'s' if n != 1 else ''}"
    return {**card, "connected": bool(cfg), "from_seed": False, "detail": detail,
            "last_sync": (cfg or {}).get("last_sync"), "read": bool(cfg), "write": False}


def github_card(cid, card):
    """Like Slack: the card is live only when a token is connected. Seeded PRs stay in the graph either way."""
    cfg = state.github_config(cid)
    detail = None
    if cfg:
        n = len(cfg.get("repos", []))
        detail = f"@{cfg.get('login', '')}, {n} repo{'s' if n != 1 else ''} selected"
    return {**card, "connected": bool(cfg), "from_seed": False, "detail": detail,
            "last_sync": (cfg or {}).get("last_sync"), "read": card["read"] and bool(cfg), "write": False}


def slack_card(cid, card):
    """The Slack card is real only when a bot is connected. The seed's Slack messages stay in the graph either way."""
    bots = [slack_bot.view(cid, cfg) for cfg in state.slack_bots(cid)]
    channels = sum(1 for b in bots for c in b["channels"] if c["listening"] and not c["im"])
    detail = (f"{len(bots)} bot{'s' if len(bots) != 1 else ''}, answering in {channels} "
              f"channel{'s' if channels != 1 else ''}") if bots else None
    return {**card, "connected": bool(bots), "from_seed": False, "detail": detail,
            "read": card["read"] and bool(bots), "write": False}


def linear_card(cid, card):
    cfg = state.linear_config(cid)
    detail = None
    if cfg:
        n = len(cfg.get("teams", []))
        detail = f"{cfg.get('name') or cfg.get('email') or 'Linear'}, {n} team{'s' if n != 1 else ''}"
    return {**card, "connected": bool(cfg), "from_seed": False, "detail": detail,
            "last_sync": (cfg or {}).get("last_sync"), "read": bool(cfg), "write": False}


def notion_card(cid, card):
    cfg = state.notion_config(cid)
    detail = None
    if cfg:
        n = len(cfg.get("databases", []))
        who = cfg.get("workspace") or cfg.get("name") or "Notion"
        detail = f"{who}, {n} database{'s' if n != 1 else ''}"
    return {**card, "connected": bool(cfg), "from_seed": False, "detail": detail,
            "last_sync": (cfg or {}).get("last_sync"), "read": bool(cfg), "write": False}


@app.get("/companies/{cid}/connectors")
def get_connectors(cid: str):
    company_or_404(cid)
    live = {"slack": slack_card, "github": github_card, "jira": jira_card,
            "linear": linear_card, "notion": notion_card}
    return [live[c["id"]](cid, c) if c["id"] in live else c for c in state.connectors(cid)]


class ConnectorPatch(BaseModel):
    connected: bool | None = None
    read: bool | None = None
    write: bool | None = None


@app.patch("/companies/{cid}/connectors/{connector_id}")
def patch_connector(cid: str, connector_id: str, body: ConnectorPatch):
    company_or_404(cid)
    for card in state.connectors(cid):
        if card["id"] == connector_id:
            for k, v in body.model_dump(exclude_none=True).items():
                card[k] = v
            if card["write"] and not card["read"]:
                card["write"] = False
            state.save()
            return card
    raise HTTPException(404, "connector not found")


@app.post("/companies/{cid}/connectors/{connector_id}/sync")
def sync_connector(cid: str, connector_id: str):
    company_or_404(cid)
    for card in state.connectors(cid):
        if card["id"] == connector_id:
            if connector_id == "upload":
                return {"ok": True, "message": "Upload has nothing to sync. Add files on Onboarding."}
            if cid == companies.LUMEN and card["from_seed"]:
                card["last_sync"] = "seed"
                return {"ok": True, "message": f"{card['name']} is loaded from the Lumen seed."}
            return {"ok": False, "message": f"Paste a {card['name']} token to sync live data. "
                                            "Token sync is not built yet."}
    raise HTTPException(404, "connector not found")
