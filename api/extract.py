"""Turn one uploaded document into a bundle (nodes + links) for loader.load_bundle.

Rules run first, so it works with no model key. They only write what they can point at in
the file: the Doc itself, people/teams/systems named in a recognised sentence or bullet,
ownership statements, and decisions. A file with no names becomes one Doc and no links.
When a model is connected, a second pass (extract_llm) adds facts the rules missed, but
only ones whose quoted sentence really appears in the file.
"""
import io
import re

import db
import extract_llm
import llm
import names
from companies import slugify

PERSON = r"[A-Z][a-z]+(?:\s[A-Z][a-z]+)?"
SYSTEM = r"[A-Z][A-Za-z0-9]*(?:\s(?:[A-Z][A-Za-z0-9]*))*"

OWNS_RE = re.compile(rf"\b(?P<p>{PERSON})\s+(?:now\s+|currently\s+)?owns\s+(?:the\s+)?(?P<s>{SYSTEM})")
OWNED_BY_RE = re.compile(rf"\b(?P<s>{SYSTEM})\s+is\s+owned\s+by\s+(?P<p>{PERSON})")
TAKES_OVER_RE = re.compile(rf"\b(?P<p>{PERSON})\s+(?:takes|will take|is taking)\s+over\s+(?:the\s+)?(?P<s>{SYSTEM})")
BULLET_RE = re.compile(r"^\s*[-*]\s+(?P<name>[A-Z][a-z]+(?:\s[A-Z][a-z]+)+)\s*[—–-]\s*(?P<role>.+?)\s*$")
HEADING_RE = re.compile(r"^#{2,3}\s+(?P<h>.+?)\s*$")
PROPOSAL_WORDS = ("starting", "takes over", "take over", "will own", "from now on", "moving off", "as of")


def read_text(filename, raw):
    if filename.lower().endswith(".pdf"):
        try:
            from pypdf import PdfReader
        except ImportError as err:
            raise ValueError("PDF support needs pypdf") from err
        reader = PdfReader(io.BytesIO(raw))
        return "\n".join((p.extract_text() or "") for p in reader.pages)
    return raw.decode("utf-8", errors="replace")


def front_matter(text):
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.S)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip().lower()] = v.strip()
    return meta, text[m.end():]


class Bundle:
    def __init__(self):
        self.nodes, self.links, self.notes, self.proposals = {}, [], [], []
        self._link_keys = set()

    def node(self, label, node_id, name, **props):
        key = (label, node_id)
        self.nodes.setdefault(key, {"label": label, "id": node_id,
                                    "props": {"name": name, "source": "upload", **props}})
        return node_id

    def link(self, src, rel, dst, **props):
        key = (src, rel, dst)
        if key not in self._link_keys:
            self._link_keys.add(key)
            self.links.append({"src": list(src), "rel": rel, "dst": list(dst), "props": props})

    def as_dict(self):
        return {"nodes": list(self.nodes.values()), "links": self.links}


def _entities(g, label):
    return [(r[0], r[1]) for r in db.read(f"MATCH (n:{label}) RETURN n.id, n.name", None, g)]


def extract(filename, raw, g, model=None):
    """`model` is a usable provider config from state.model_config, or None for rules only."""
    text = read_text(filename, raw)
    meta, body = front_matter(text)
    b = Bundle()
    stem = re.sub(r"\.[A-Za-z0-9]+$", "", filename.split("/")[-1].split("\\")[-1])
    heading = re.search(r"^#\s+(.+)$", body, re.M)
    title = meta.get("title") or (heading.group(1).strip() if heading else stem)
    date = meta.get("date") or db.TODAY
    doc_id = f"doc-{slugify(stem)}"
    b.node("Doc", doc_id, title.split(":")[0].strip() if title.upper().startswith("ADR") else title,
           title=title, body=body[:20000], date=date, url=filename, status=meta.get("status", "note"))
    doc = ("Doc", doc_id)
    b.notes.append(f"Doc: {title}")

    people_idx = names.unique_alias_index(_entities(g, "Person"), names.person_aliases)
    system_idx = names.unique_alias_index(_entities(g, "System"), names.system_aliases)
    team_idx = {n.lower(): i for i, n in _entities(g, "Team")}
    people_names = {i: n for i, n in _entities(g, "Person")}

    def person(raw_name, role=None):
        key = raw_name.strip().lower()
        pid = people_idx.get(key) or people_idx.get(key.split()[0]) or people_idx.get(key.split()[-1])
        if pid is None:
            pid = slugify(raw_name)
            props = {"role": role} if role else {}
            b.node("Person", pid, raw_name.strip(), **props)
            people_idx[key] = pid
            people_names[pid] = raw_name.strip()
            b.notes.append(f"Person: {raw_name.strip()}")
        elif role:
            b.node("Person", pid, people_names.get(pid, raw_name.strip()), role=role)
        return pid

    def system(raw_name):
        key = raw_name.strip().lower()
        sid = system_idx.get(key)
        if sid is None:
            tokens = [t for t in key.split() if t not in names.GENERIC]
            sid = system_idx.get(" ".join(tokens)) if tokens else None
        if sid is None:
            sid = f"sys-{slugify(raw_name)}"
            b.node("System", sid, raw_name.strip())
            system_idx[key] = sid
            b.notes.append(f"System: {raw_name.strip()}")
        return sid

    # author
    author = meta.get("author")
    if not author:
        m = re.search(r"^\s*(?:author|by)\s*:\s*(.+)$", body, re.M | re.I)
        author = m.group(1).strip() if m else None
    if author:
        b.link(("Person", person(author)), "AUTHORED", doc)

    # team directory: "## Engineering" followed by "- Priya Shah — Eng lead"
    team = None
    for line in body.splitlines():
        h = HEADING_RE.match(line)
        if h:
            team = h.group("h").strip()
            continue
        m = BULLET_RE.match(line)
        if m and team:
            pid = person(m.group("name"), m.group("role"))
            tid = team_idx.get(team.lower()) or f"team-{slugify(team)}"
            if team.lower() not in team_idx:
                b.node("Team", tid, team)
                team_idx[team.lower()] = tid
                b.notes.append(f"Team: {team}")
            b.link(("Person", pid), "MEMBER_OF", ("Team", tid))

    # ownership: only an unowned system gets OWNS straight from a document; any change of
    # owner, or wording that sounds like a handoff, becomes a proposal an admin must Apply.
    def ownership(p_raw, s_raw, proposal, tag=""):
        pid, sid = person(p_raw), system(s_raw)
        b.link(doc, "SOURCES", ("System", sid))
        cur = db.read(
            """MATCH (p:Person)-[o:OWNS]->(s:System {id: $sid}) WHERE o.end IS NULL
               RETURN p.id""", {"sid": sid}, g)
        cur_id = cur[0][0] if cur else None
        who = people_names.get(pid, p_raw)
        if cur_id == pid:
            b.notes.append(f"Confirmed: {who} already owns {s_raw}")
        elif cur_id is None and not proposal:
            b.link(("Person", pid), "OWNS", ("System", sid), start=date, source="upload", url=filename)
            b.notes.append(f"{tag}OWNS: {who} owns {s_raw}")
        else:
            b.link(doc, "PROPOSES", ("System", sid), start=date, owner=pid, system=sid)
            b.proposals.append({"owner": pid, "system": sid, "doc": doc_id})
            b.notes.append(f"{tag}PROPOSES: {who} for {s_raw} (not applied)")

    sentences = re.split(r"(?<=[.!?])\s+|\n+", body)
    for sent in sentences:
        for rx in (OWNS_RE, OWNED_BY_RE, TAKES_OVER_RE):
            for m in rx.finditer(sent):
                # "starting" etc. is lowercase so SYSTEM already stopped before it
                ownership(m.group("p"), m.group("s"),
                          rx is TAKES_OVER_RE or any(w in sent.lower() for w in PROPOSAL_WORDS))

    # decision
    status_line = re.search(r"^\s*status\s*:\s*(\w+)", body, re.M | re.I)
    status = (meta.get("status") or (status_line.group(1) if status_line else "")).lower()
    if status not in {"accepted", "proposed", "rejected", "canceled", "superseded"}:
        status = ""
    if title.upper().startswith("ADR") or status:
        decision_text = title.split(":", 1)[1].strip() if ":" in title else title
        did = f"decision-{slugify(stem)}"
        b.node("Decision", did, decision_text, text=decision_text,
               status=(status or "accepted").lower(), date=date, url=filename)
        b.link(("Decision", did), "WRITTEN_IN", doc)
        if author:
            b.link(("Person", person(author)), "DECIDES", ("Decision", did))
        b.notes.append(f"Decision: {decision_text}")
        for sid in names.find_in_text(body, {i: names.system_aliases(n) for i, n in _entities(g, "System")}
                                      | {k[1]: names.system_aliases(v["props"]["name"])
                                         for k, v in b.nodes.items() if k[0] == "System"}):
            b.link(("Decision", did), "ABOUT", ("System", sid))

    # model pass: adds what the rules could not read. Every fact must quote the file.
    if model:
        try:
            found = extract_llm.facts(model, body, set(people_names.values()),
                                      {n for _, n in _entities(g, "System")}
                                      | {v["props"]["name"] for k, v in b.nodes.items() if k[0] == "System"})
        except llm.LLMError as err:
            b.notes.append(f"Model skipped ({err}). Used the rules only.")
        else:
            added = 0
            for p in found["people"]:
                pid = person(p["name"], p["role"] or None)
                added += 1
                if p["team"]:
                    tid = team_idx.get(p["team"].lower()) or f"team-{slugify(p['team'])}"
                    if p["team"].lower() not in team_idx:
                        b.node("Team", tid, p["team"])
                        team_idx[p["team"].lower()] = tid
                        b.notes.append(f"Team: {p['team']}")
                    b.link(("Person", pid), "MEMBER_OF", ("Team", tid))
            for o in found["ownership"]:
                added += 1
                ownership(o["person"], o["system"],
                          o["proposed"] or any(w in o["evidence"].lower() for w in PROPOSAL_WORDS), tag="Model · ")
            d = found["decision"]
            did = f"decision-{slugify(stem)}"
            if d and ("Decision", did) not in b.nodes:
                added += 1
                b.node("Decision", did, d["title"], text=d["title"], status=d["status"], date=date, url=filename)
                b.link(("Decision", did), "WRITTEN_IN", doc)
                if author:
                    b.link(("Person", person(author)), "DECIDES", ("Decision", did))
                for s_name in d["systems"]:
                    b.link(("Decision", did), "ABOUT", ("System", system(s_name)))
                b.notes.append(f"Model · Decision: {d['title']}")
            b.notes.append(f"Model read the file: {added} facts kept, {found['dropped']} dropped for lacking a quote.")

    # the doc is ABOUT every known or just-created system it mentions
    known = {i: names.system_aliases(n) for i, n in _entities(g, "System")}
    known |= {k[1]: names.system_aliases(v["props"]["name"]) for k, v in b.nodes.items() if k[0] == "System"}
    for sid in names.find_in_text(body, known):
        b.link(doc, "ABOUT", ("System", sid))

    return b
