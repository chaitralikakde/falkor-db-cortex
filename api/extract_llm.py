"""Model-backed fact extraction with a hard guardrail.

The model reads one document and proposes people, ownership and a decision. A fact is kept
only if the sentence it quotes really appears in the file and the names it uses appear in that
sentence. Anything the model made up fails that check and is dropped.
"""
import re

import llm

MAX_CHARS = 12000
STATUSES = {"accepted", "proposed", "rejected", "canceled", "superseded"}

SYSTEM_PROMPT = """You extract organisational facts from ONE document for a company knowledge graph.
Return ONLY a JSON object with this shape:
{
  "people": [{"name": "Full Name", "role": "job title or empty", "team": "team name or empty", "evidence": "exact sentence or bullet from the document"}],
  "ownership": [{"person": "Full Name", "system": "System Name", "status": "current" or "proposed", "evidence": "exact sentence from the document"}],
  "decision": null or {"title": "short decision", "status": "accepted|proposed|rejected|canceled|superseded", "systems": ["System Name"], "evidence": "exact sentence from the document"}
}
Rules:
- Include a fact only if a sentence in the document states it. Copy that sentence into "evidence" exactly as written.
- Never infer, guess, or use outside knowledge. If the document names nothing relevant, return empty lists and null.
- "current" ownership: the document says someone owns a system now. "proposed": someone will take over, is moving to, or a handoff is planned or not yet done.
- A system is a service, product, repo or component (for example Billing Service). Do not list people or teams as systems.
- Use the spellings from KNOWN NAMES when the document refers to the same person or system by a short form."""


def _norm(s):
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def _has(evidence_n, name):
    n = _norm(name)
    return bool(n) and re.search(rf"(?<!\w){re.escape(n)}(?!\w)", evidence_n) is not None


def facts(model, body, known_people, known_systems):
    """Validated facts: {"people": [...], "ownership": [...], "decision": {...}|None, "dropped": int}."""
    known = (f"KNOWN NAMES\nPeople: {', '.join(sorted(known_people)[:80]) or 'none'}\n"
             f"Systems: {', '.join(sorted(known_systems)[:80]) or 'none'}")
    text = body[:MAX_CHARS]
    reply = llm.chat(
        model,
        [{"role": "system", "content": SYSTEM_PROMPT},
         {"role": "user", "content": f"{known}\n\nDOCUMENT\n{text}"}],
        json_mode=True, max_tokens=1800)
    raw = llm.parse_json(reply)
    if not isinstance(raw, dict):
        raise llm.LLMError("The model returned the wrong shape.")

    body_n = _norm(text)
    dropped = 0

    def quoted(item):
        ev = _norm(item.get("evidence"))
        return len(ev) >= 8 and ev in body_n, ev

    people = []
    for p in (raw.get("people") or [])[:60]:
        if not isinstance(p, dict):
            continue
        ok, ev = quoted(p)
        name = str(p.get("name") or "").strip()
        parts = name.split()
        if ok and name and (_has(ev, name) or (len(parts) > 1 and (_has(ev, parts[0]) or _has(ev, parts[-1])))):
            people.append({"name": name, "role": str(p.get("role") or "").strip(),
                           "team": str(p.get("team") or "").strip(), "evidence": p["evidence"]})
        else:
            dropped += 1

    ownership = []
    for o in (raw.get("ownership") or [])[:60]:
        if not isinstance(o, dict):
            continue
        ok, ev = quoted(o)
        person, system = str(o.get("person") or "").strip(), str(o.get("system") or "").strip()
        parts = person.split()
        person_ok = _has(ev, person) or any(_has(ev, t) for t in parts)
        if ok and person and system and person_ok and _has(ev, system):
            ownership.append({"person": person, "system": system,
                              "proposed": o.get("status") == "proposed", "evidence": o["evidence"]})
        else:
            dropped += 1

    decision = None
    d = raw.get("decision")
    if isinstance(d, dict):
        ok, _ = quoted(d)
        status = str(d.get("status") or "").lower()
        title = str(d.get("title") or "").strip()
        if ok and title and status in STATUSES:
            decision = {"title": title, "status": status, "evidence": d["evidence"],
                        "systems": [str(s).strip() for s in (d.get("systems") or []) if str(s).strip()][:10]}
        else:
            dropped += 1

    return {"people": people, "ownership": ownership, "decision": decision, "dropped": dropped}
