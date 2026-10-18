"""propose_handoff (Clerk) and apply_handoff (admin button). Only Apply changes OWNS."""
import db


def _name(g, label, node_id):
    rows = db.read(f"MATCH (n:{label} {{id: $id}}) RETURN n.name", {"id": node_id}, g)
    return rows[0][0] if rows else node_id


def open_task(g, system_id, owner_id=None):
    rows = db.read(
        """MATCH (t:Task {status: 'open'})-[:ABOUT]->(:System {id: $sid})
           MATCH (t)-[:ASSIGNS]->(p:Person)
           RETURN t.id, p.id""",
        {"sid": system_id}, g,
    )
    for tid, pid in rows:
        if owner_id is None or pid == owner_id:
            return tid
    return None


def propose_handoff(g, system_id, owner_id, source_refs):
    """Write a Task (and its links). Does not touch OWNS. source_refs: [(label, id)]."""
    existing = open_task(g, system_id, owner_id)
    if existing:
        return existing, False
    owner = _name(g, "Person", owner_id)
    system = _name(g, "System", system_id)
    task_id = f"task-{system_id}-{owner_id}"
    title = f"Confirm {owner} as {system} owner"
    db.merge_node("Task", task_id, {"name": title, "title": title, "status": "open",
                                    "created": db.TODAY, "source": "clerk"}, g)
    db.merge_link("Task", task_id, "ASSIGNS", "Person", owner_id, {}, g)
    db.merge_link("Task", task_id, "ABOUT", "System", system_id, {}, g)
    for label, sid in source_refs:
        db.merge_link("Task", task_id, "SOURCES", label, sid, {}, g)
    db.merge_link("Agent", "agent-clerk", "WROTE", "Task", task_id, {}, g)
    return task_id, True


def list_tasks(g):
    rows = db.read(
        """MATCH (t:Task)-[:ASSIGNS]->(p:Person)
           MATCH (t)-[:ABOUT]->(s:System)
           OPTIONAL MATCH (cur:Person)-[o:OWNS]->(s) WHERE o.end IS NULL
           OPTIONAL MATCH (t)-[:SOURCES]->(src)
           RETURN t, p, s, cur, collect(DISTINCT src)""",
        None, g,
    )
    out = []
    for t, p, s, cur, srcs in rows:
        out.append({
            "id": t.properties["id"],
            "title": t.properties.get("title") or t.properties.get("name"),
            "status": t.properties.get("status"),
            "created": t.properties.get("created", ""),
            "assignee": {"id": p.properties["id"], "name": p.properties.get("name")},
            "system": {"id": s.properties["id"], "name": s.properties.get("name")},
            "current_owner": cur.properties.get("name") if cur else None,
            "sources": [
                {"id": x.properties["id"], "kind": x.labels[0],
                 "name": x.properties.get("name") or x.properties.get("key"),
                 "url": x.properties.get("url", "")}
                for x in srcs
            ],
        })
    out.sort(key=lambda r: (r["status"] != "open", r["title"] or ""))
    return out


def apply_handoff(g, task_id):
    rows = db.read(
        """MATCH (t:Task {id: $id})-[:ASSIGNS]->(p:Person)
           MATCH (t)-[:ABOUT]->(s:System)
           RETURN t.status, p.id, p.name, s.id, s.name""",
        {"id": task_id}, g,
    )
    if not rows:
        raise LookupError("task not found")
    status, new_id, new_name, sys_id, sys_name = rows[0]
    if status != "open":
        raise ValueError("task already applied")
    today = db.TODAY

    ended = db.read(
        """MATCH (old:Person)-[o:OWNS]->(s:System {id: $sid})
           WHERE o.end IS NULL AND old.id <> $new
           RETURN old.id, old.name, o.start""",
        {"sid": sys_id, "new": new_id}, g,
    )
    # 1. end the old OWNS (the link stays)
    db.write(
        """MATCH (old:Person)-[o:OWNS]->(s:System {id: $sid})
           WHERE o.end IS NULL AND old.id <> $new
           SET o.end = $today""",
        {"sid": sys_id, "new": new_id, "today": today}, g,
    )
    # 2. start the new OWNS
    db.merge_link("Person", new_id, "OWNS", "System", sys_id, {"start": today}, g)
    # 3. the proposals are now applied, and the new owner joins the project that uses the system
    db.write(
        """MATCH (src)-[r:PROPOSES]->(s:System {id: $sid})
           WHERE r.owner = $new
           SET r.applied = true""",
        {"sid": sys_id, "new": new_id}, g,
    )
    db.write(
        """MATCH (proj:Project)-[:USES]->(:System {id: $sid})
           MATCH (p:Person {id: $new})
           MERGE (p)-[w:WORKS_ON]->(proj)
           ON CREATE SET w.since = $today""",
        {"sid": sys_id, "new": new_id, "today": today}, g,
    )
    # 4. the task is done
    db.write(
        "MATCH (t:Task {id: $id}) SET t += {status: 'done', done: $today}",
        {"id": task_id, "today": today}, g,
    )
    return {
        "task": task_id,
        "system": {"id": sys_id, "name": sys_name},
        "new_owner": {"id": new_id, "name": new_name, "start": today},
        "ended": [{"id": i, "name": n, "start": s, "end": today} for i, n, s in ended],
    }
