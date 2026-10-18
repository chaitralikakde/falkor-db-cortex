"""Mapper's read tools. Every tool runs parameterised Cypher with ro_query and returns
the rows, the nodes/links they touched, the Cypher text, and the time."""
import db
import graphio


def _ref(n):
    p = n.properties
    return {
        "id": p["id"],
        "kind": n.labels[0] if n.labels else "",
        "name": graphio.label_for(n.labels[0] if n.labels else "", p),
        "url": p.get("url", ""),
        "date": p.get("date") or p.get("opened") or p.get("at") or "",
    }


def _run(tool, g, cypher, params):
    rows, ms = db.read_full(cypher, params, g)
    nodes, links = graphio.collect(rows)
    return {"tool": tool, "cypher": " ".join(cypher.split()), "rows": rows,
            "nodes": nodes, "links": links, "ms": ms}


def list_systems(g, department=None):
    """System names the caller may see. A department bot only sees systems labelled with that id."""
    if department:
        rows = db.read("MATCH (s:System {department: $d}) RETURN s.name", {"d": department}, g)
    else:
        rows = db.read("MATCH (s:System) RETURN s.name", None, g)
    return [r[0] for r in rows]


def latest_session_system(g, department=None):
    if department:
        rows = db.read(
            """MATCH (s:Session)-[:RECALLS]->(sys:System {department: $d})
               WITH sys, s ORDER BY s.at DESC LIMIT 1
               RETURN sys.name""",
            {"d": department}, g,
        )
    else:
        rows = db.read(
            """MATCH (s:Session)-[:RECALLS]->(sys:System)
               WITH sys, s ORDER BY s.at DESC LIMIT 1
               RETURN sys.name""",
            None, g,
        )
    return rows[0][0] if rows else None


def recall_session(g, system):
    res = _run(
        "recall_session", g,
        """MATCH (s:Session)-[:RECALLS]->(:System {name: $name})
           WITH s ORDER BY s.at DESC LIMIT 1
           MATCH (s)-[r:RECALLS]->(n)
           RETURN s, r, n""",
        {"name": system},
    )
    facts = None
    if res["rows"]:
        s = res["rows"][0][0].properties
        facts = {
            "id": s["id"], "at": s.get("at", ""), "question": s.get("question", ""),
            "asked_by": s.get("asked_by", ""), "conclusion": s.get("conclusion", ""),
            "refs": [_ref(r[2]) for r in res["rows"]],
        }
    res["facts"] = facts
    return res


def find_owner(g, system):
    cur = _run(
        "find_owner", g,
        """MATCH (p:Person)-[o:OWNS]->(s:System {name: $name})
           WHERE o.end IS NULL
           RETURN p, o, s""",
        {"name": system},
    )
    prev = _run(
        "find_owner:history", g,
        """MATCH (p:Person)-[o:OWNS]->(s:System {name: $name})
           WHERE o.end IS NOT NULL
           RETURN p, o, s ORDER BY o.end DESC""",
        {"name": system},
    )
    pend = _run(
        "find_owner:pending", g,
        """MATCH (src)-[r:PROPOSES]->(s:System {name: $name})
           WHERE r.applied IS NULL
           OPTIONAL MATCH (po:Person) WHERE po.id = r.owner
           RETURN src, r, s, po""",
        {"name": system},
    )
    facts = {"owner": None, "previous": [], "pending": []}
    if cur["rows"]:
        p, o, s = cur["rows"][0]
        facts["owner"] = {**_ref(p), "start": o.properties.get("start", ""), "system": _ref(s)}
    for p, o, s in prev["rows"]:
        facts["previous"].append({**_ref(p), "start": o.properties.get("start", ""),
                                  "end": o.properties.get("end", "")})
    for src, r, s, po in pend["rows"]:
        facts["pending"].append({
            "source": _ref(src),
            "owner": _ref(po) if po else None,
            "system": {"id": s.properties["id"], "name": s.properties.get("name")},
            "start": r.properties.get("start", ""),
        })
    nodes, links = [], []
    for part in (cur, prev, pend):
        nodes += part["nodes"]
        links += part["links"]
    return {"tool": "find_owner", "cypher": cur["cypher"], "ms": round(cur["ms"] + prev["ms"] + pend["ms"], 2),
            "rows": cur["rows"] + prev["rows"] + pend["rows"], "nodes": nodes, "links": links,
            "facts": facts}


def find_experts(g, system):
    res = _run(
        "find_experts", g,
        """MATCH (p:Person)-[a:AUTHORED|REVIEWED]->(pr:PullRequest)-[c:CHANGES]->(s:System {name: $name})
           RETURN p, a, pr, c, s""",
        {"name": system},
    )
    people = {}
    for p, a, pr, c, s in res["rows"]:
        e = people.setdefault(p.properties["id"], {**_ref(p), "authored": [], "reviewed": []})
        bucket = "authored" if a.relation == "AUTHORED" else "reviewed"
        e[bucket].append(_ref(pr))
    experts = []
    for e in people.values():
        e["count"] = len({x["id"] for x in e["authored"] + e["reviewed"]})
        experts.append(e)
    experts.sort(key=lambda e: (-e["count"], e["name"]))
    res["facts"] = {"experts": experts}
    return res


def find_decision(g, system):
    dec = _run(
        "find_decision", g,
        """MATCH (d:Decision {status: 'accepted'})-[ab:ABOUT]->(s:System {name: $name})
           OPTIONAL MATCH (d)-[w:WRITTEN_IN]->(doc)
           OPTIONAL MATCH (d)-[so:SOURCES]->(src)
           OPTIONAL MATCH (old:Decision)-[rb:REPLACED_BY]->(d)
           OPTIONAL MATCH (old)-[ow:WRITTEN_IN|SOURCES]->(osrc)
           RETURN d, ab, s, doc, w, src, so, old, rb, osrc, ow""",
        {"name": system},
    )
    work = _run(
        "find_decision:project", g,
        """MATCH (p:Person)-[wo:WORKS_ON]->(proj:Project)-[u:USES]->(s:System {name: $name})
           MATCH (d:Decision {status: 'accepted'})-[ab:ABOUT]->(proj)
           RETURN p, wo, proj, u, s, d, ab""",
        {"name": system},
    )
    facts = {"decision": None, "written_in": [], "sources": [], "replaced": None,
             "replaced_sources": [], "project": None, "people": []}
    seen = {"written_in": set(), "sources": set(), "replaced_sources": set()}
    for d, ab, s, doc, w, src, so, old, rb, osrc, ow in dec["rows"]:
        if facts["decision"] is None:
            facts["decision"] = {**_ref(d), "text": d.properties.get("text", ""),
                                 "status": d.properties.get("status", "")}
        if doc is not None and doc.properties["id"] not in seen["written_in"]:
            seen["written_in"].add(doc.properties["id"])
            facts["written_in"].append(_ref(doc))
        if src is not None and src.properties["id"] not in seen["sources"]:
            seen["sources"].add(src.properties["id"])
            facts["sources"].append(_ref(src))
        if old is not None and facts["replaced"] is None:
            facts["replaced"] = {**_ref(old), "text": old.properties.get("text", ""),
                                 "status": old.properties.get("status", "")}
        if osrc is not None and osrc.properties["id"] not in seen["replaced_sources"]:
            seen["replaced_sources"].add(osrc.properties["id"])
            facts["replaced_sources"].append(_ref(osrc))
    people = {}
    for p, wo, proj, u, s, d, ab in work["rows"]:
        people[p.properties["id"]] = _ref(p)
        facts["project"] = _ref(proj)
    facts["people"] = list(people.values())
    nodes = dec["nodes"] + [n for n in work["nodes"]]
    links = dec["links"] + work["links"]
    return {"tool": "find_decision", "cypher": dec["cypher"], "ms": round(dec["ms"] + work["ms"], 2),
            "rows": dec["rows"] + work["rows"], "nodes": nodes, "links": links, "facts": facts}
