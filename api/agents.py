"""Mapper and Clerk. They share state only through FalkorDB.

Mapper runs the Cypher tools and writes a Finding on a new Session.
Clerk loads that Finding from FalkorDB, may write a PROPOSES-backed Task, and phrases
the answer using only names that are in the Finding.
"""
import json
import re
import time
import uuid

import db
import departments
import graphio
import handoff
import names
import tools

NO_SOURCE = "I can't find a source."


# ----------------------------------------------------------------- intent --
def classify(question):
    q = question.lower()
    if any(w in q for w in ["already", "earlier", "last time", "remember", "previous session", "before"]):
        return "recall"
    if any(w in q for w in ["why", "decid", "decision", "migrat", "postgres", "mysql", "adr", "move the"]):
        return "decision"
    if any(w in q for w in ["who", "owner", "owns", " own ", "fix", "expert", "knows", "maintain", "contact"]):
        return "owner"
    return None


SKILL_FOR = {"owner": "Who owns this", "decision": "Why we decided this"}


def resolve_system(g, question, use_context=True, department=None):
    systems = tools.list_systems(g, department)
    found = names.find_in_text(question, {s: names.system_aliases(s) for s in systems})
    if found:
        return found[0], False
    # The web Ask is one person's running conversation, so "Who owns it?" and "Why did we move
    # the database?" mean what the last session was about. Shared channels turn that off: there
    # "it" could be anyone's earlier question, so a question that names nothing known is refused.
    if use_context:
        return tools.latest_session_system(g, department), True
    return None, False


# ------------------------------------------------------------------ Mapper --
def _step(agent, res, label=None):
    return {
        "agent": agent,
        "tool": label or res["tool"],
        "cypher": res["cypher"],
        "ms": res["ms"],
        "nodes": res["nodes"],
        "links": res["links"],
    }


def _write_finding(g, question, intent, system, facts, nodes, asked_by="You"):
    stamp = time.strftime("%H%M%S")
    sid = f"session-{db.TODAY.replace('-', '')}-{stamp}-{uuid.uuid4().hex[:4]}"
    fid = sid.replace("session", "finding", 1)
    body = json.dumps({"question": question, "intent": intent, "system": system, "facts": facts})
    db.merge_node("Session", sid, {
        "name": sid, "question": question, "at": f"{db.TODAY}T{time.strftime('%H:%M')}",
        "asked_by": asked_by, "conclusion": "", "source": "ask"}, g)
    db.merge_node("Finding", fid, {
        "name": fid, "tool": ",".join(facts.get("_tools", [])), "body": body, "source": "mapper"}, g)
    db.merge_link("Finding", fid, "FOUND", "Session", sid, {}, g)
    db.merge_link("Session", sid, "RAN", "Agent", "agent-mapper", {}, g)
    db.merge_link("Session", sid, "RAN", "Agent", "agent-clerk", {}, g)
    key_kinds = {"System", "Decision", "Doc"}
    recalled = [n for n in nodes if n["label"] in key_kinds or n["id"] in facts.get("_recall_ids", [])]
    for n in recalled:
        db.merge_link("Session", sid, "RECALLS", n["label"], n["id"], {}, g)
        db.merge_link("Finding", fid, "FOUND", n["label"], n["id"], {}, g)
    return sid, fid


def _mapper(g, question, intent, system):
    steps, all_nodes = [], []
    facts = {"_tools": []}

    def take(res, agent="Mapper", label=None):
        steps.append(_step(agent, res, label))
        all_nodes.extend(res["nodes"])
        facts["_tools"].append(res["tool"])

    rec = tools.recall_session(g, system)       # always first
    take(rec)
    facts["recall"] = rec["facts"]

    if intent == "owner":
        own = tools.find_owner(g, system)
        take(own)
        facts.update(own["facts"])
        exp = tools.find_experts(g, system)
        take(exp)
        facts.update(exp["facts"])
        facts["_recall_ids"] = [x["id"] for x in
                                ([own["facts"]["owner"]] if own["facts"]["owner"] else [])]
    elif intent == "decision":
        dec = tools.find_decision(g, system)
        take(dec)
        facts.update(dec["facts"])
    # intent == "recall": the recall step is the whole answer

    facts["system_name"] = system
    return steps, facts, all_nodes


# ------------------------------------------------------------------- Clerk --
def _read_finding(g, fid):
    rows, ms = db.read_full(
        "MATCH (f:Finding {id: $id})-[:FOUND]->(n) RETURN f, n", {"id": fid}, g)
    if not rows:
        return None, [], [], ms
    body = json.loads(rows[0][0].properties["body"])
    nodes, links = graphio.collect(rows)
    return body, nodes, links, ms


def _src(refs):
    out, seen = [], set()
    for r in refs:
        if r and r["id"] not in seen and r.get("url") is not None:
            seen.add(r["id"])
            out.append({k: r.get(k, "") for k in ("id", "kind", "name", "url", "date")})
    return out


def _join(items):
    items = [i for i in items if i]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _phrase(body):
    """Phrase the answer from the Finding body only. Returns (sentence, sources, has_answer)."""
    f, intent, system = body["facts"], body["intent"], body["system"]
    lines, refs = [], []

    if intent == "recall":
        rec = f.get("recall")
        if not rec:
            return NO_SOURCE, [], False
        lines.append(f"On {rec['at'][:10]} {rec['asked_by'] or 'someone'} asked \"{rec['question']}\". "
                     f"The stored conclusion: {rec['conclusion']}")
        refs += rec["refs"]
        return "\n".join(lines), _src(refs), True

    if intent == "owner":
        owner = f.get("owner")
        if not owner:
            return NO_SOURCE, [], False
        lines.append(f"{owner['name']} owns {system}, since {owner['start']}.")
        refs += [owner, owner["system"]]
        rec = f.get("recall")
        if rec:
            said = rec["conclusion"]
            prev = f["previous"][0] if f["previous"] else None
            if owner["name"] in said:
                lines.append(f"This matches what the session on {rec['at'][:10]} already recorded.")
            elif prev and prev["name"] in said:
                lines.append(f"The owner changed: {prev['name']} owned it from {prev['start']} to {prev['end']}. "
                             f"The session on {rec['at'][:10]} still shows {prev['name']}.")
        if f["pending"]:
            p = f["pending"][0]
            who = p["owner"]["name"] if p["owner"] else "someone else"
            srcs = _join(sorted({x["source"]["name"] for x in f["pending"]}))
            lines.append(f"A handoff to {who} is proposed in {srcs}, but it is not applied yet.")
            refs += [x["source"] for x in f["pending"]]
        others = [e for e in f.get("experts", []) if e["id"] != owner["id"]]
        if others:
            parts = []
            for e in others:
                bits = []
                if e["authored"]:
                    bits.append("authored " + _join([x["name"] for x in e["authored"]]))
                if e["reviewed"]:
                    bits.append("reviewed " + _join([x["name"] for x in e["reviewed"]]))
                parts.append(f"{e['name']} ({'; '.join(bits)})")
                refs += e["authored"] + e["reviewed"]
            lines.append("Others who have touched it: " + _join(parts) + ".")
        else:
            lines.append("Nobody else has authored or reviewed a change to it.")
        return "\n".join(lines), _src(refs), True

    if intent == "decision":
        d = f.get("decision")
        if not d:
            return NO_SOURCE, [], False
        where = _join([f"{x['name']} ({x['date']})" if x["date"] else x["name"] for x in f["written_in"]])
        text = f"The current decision about {system} is \"{d['text']}\" ({d['status']})"
        text += f", written in {where}." if where else "."
        lines.append(text)
        refs += [d] + f["written_in"]
        if f["sources"]:
            lines.append("It is sourced by " + _join([x["name"] for x in f["sources"]]) + ".")
            refs += f["sources"]
        if f["replaced"]:
            old = f["replaced"]
            via = _join([x["name"] for x in f["replaced_sources"]])
            lines.append(f"It replaced \"{old['text']}\" ({old['status']})" + (f", tracked in {via}." if via else "."))
            refs += [old] + f["replaced_sources"]
        if f["project"] and f["people"]:
            lines.append(f"{_join([p['name'] for p in f['people']])} work on {f['project']['name']}, "
                         f"which uses {system}.")
            refs += [f["project"]] + f["people"]
        return "\n".join(lines), _src(refs), True

    return NO_SOURCE, [], False


def _clerk(g, fid, sid):
    steps = []
    body, nodes, links, ms = _read_finding(g, fid)
    steps.append({
        "agent": "Clerk", "tool": "read_finding",
        "cypher": "MATCH (f:Finding {id: $id})-[:FOUND]->(n) RETURN f, n",
        "ms": ms, "nodes": nodes, "links": links,
    })
    if body is None:
        return steps, NO_SOURCE, [], False

    sentence, sources, ok = _phrase(body)

    # A PROPOSES link in the rows means a handoff Task has to exist. Writes a Task, never OWNS.
    pending = body["facts"].get("pending") or []
    for p in pending:
        if p["owner"]:
            started = time.perf_counter()
            task_id, created = handoff.propose_handoff(
                g, p["system"]["id"], p["owner"]["id"],
                [(p["source"]["kind"], p["source"]["id"])])
            rows, _ = db.read_full(
                """MATCH (t:Task {id: $id})-[a:ASSIGNS]->(who:Person)
                   MATCH (t)-[b:ABOUT]->(s:System)
                   OPTIONAL MATCH (t)-[c:SOURCES]->(src)
                   OPTIONAL MATCH (ag:Agent {id: 'agent-clerk'})-[w:WROTE]->(t)
                   RETURN t, a, who, b, s, c, src, ag, w""", {"id": task_id}, g)
            tn, tl = graphio.collect(rows)
            task_name = rows[0][0].properties.get("name", task_id) if rows else task_id
            steps.append({
                "agent": "Clerk", "tool": "propose_handoff",
                "cypher": "MERGE (t:Task) … ASSIGNS, ABOUT, SOURCES  (OWNS unchanged)",
                "ms": round((time.perf_counter() - started) * 1000, 2),
                "nodes": tn, "links": tl,
            })
            sentence += f"\nClerk {'wrote' if created else 'confirmed'} the task \"{task_name}\". An admin has to Apply it on the Graph page."
            break

    if ok:
        db.write("MATCH (s:Session {id: $id}) SET s.conclusion = $c",
                 {"id": sid, "c": sentence.replace("\n", " ")}, g)
    return steps, sentence, sources, ok


# ------------------------------------------------------------------- ask ---
def ask(g, question, settings, asked_by="You", use_context=True, department=None):
    started = time.perf_counter()
    refusal = lambda msg: {"sentence": msg, "sources": [], "steps": [], "refused": True,
                           "session": None, "finding": None,
                           "ms": round((time.perf_counter() - started) * 1000, 2)}

    intent = classify(question)
    if intent is None:
        return refusal(NO_SOURCE)
    skill = SKILL_FOR.get(intent)
    if skill and not any(s["name"] == skill and s["on"] for s in settings["skills"]):
        return refusal(f"The \"{skill}\" skill is off. An admin can turn it on under Skills.")

    system, inferred = resolve_system(g, question, use_context, departments.known(department))
    if not system:
        return refusal(NO_SOURCE)

    steps, facts, nodes = _mapper(g, question, intent, system)
    answerable = {
        "recall": bool(facts.get("recall")),
        "owner": bool(facts.get("owner")),
        "decision": bool(facts.get("decision")),
    }[intent]
    if not answerable:
        out = refusal(NO_SOURCE)
        out["steps"] = steps
        return out

    sid, fid = _write_finding(g, question, intent, system, facts, nodes, asked_by)
    rows, ms = db.read_full(
        """MATCH (fi:Finding {id: $fid})-[f:FOUND]->(s:Session {id: $sid})
           MATCH (s)-[r:RAN]->(ag:Agent)
           RETURN fi, f, s, r, ag""", {"fid": fid, "sid": sid}, g)
    wn, wl = graphio.collect(rows)
    steps.append({"agent": "Mapper", "tool": "write_finding",
                  "cypher": "MERGE (s:Session) MERGE (f:Finding) … FOUND, RAN, RECALLS",
                  "ms": ms, "nodes": wn, "links": wl})

    clerk_steps, sentence, sources, ok = _clerk(g, fid, sid)
    steps += clerk_steps

    # playback order: Mapper node, Clerk node, then every company node in the order it was read
    seen_n, seen_l = set(), set()
    for st in steps:
        nn, ll = [], []
        for n in st["nodes"]:
            if n["id"] not in seen_n:
                seen_n.add(n["id"])
                nn.append(n)
        for l in st["links"]:
            if l["id"] not in seen_l:
                seen_l.add(l["id"])
                ll.append(l)
        st["nodes"], st["links"] = nn, ll

    return {
        "sentence": sentence if ok else NO_SOURCE,
        "sources": sources,
        "steps": steps,
        "refused": not ok,
        "session": sid,
        "finding": fid,
        "system": system,
        "system_inferred": inferred,
        "intent": intent,
        "ms": round((time.perf_counter() - started) * 1000, 2),
    }


def answers(g, limit=30):
    rows = db.read(
        """MATCH (s:Session)
           WHERE s.source = 'ask' OR s.id = 'session-1017'
           OPTIONAL MATCH (s)-[:RECALLS]->(n)
           RETURN s, collect(DISTINCT n.name)
           ORDER BY s.at DESC LIMIT $limit""",
        {"limit": limit}, g)
    out = []
    for s, recalled in rows:
        p = s.properties
        out.append({"id": p["id"], "question": p.get("question", ""), "at": p.get("at", ""),
                    "asked_by": p.get("asked_by", ""), "conclusion": p.get("conclusion", ""),
                    "nodes": recalled})
    return out
