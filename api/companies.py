"""Company registry. Lives in its own FalkorDB graph; each company gets its own graph."""
import re

import db
import loader

LUMEN = "lumen"


def slugify(text):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "company"


def _row(r):
    c = r[0].properties
    return {
        "id": c["id"],
        "name": c["name"],
        "graph": c["graph"],
        "finished": bool(c.get("finished")),
        "admin": c.get("admin", ""),
        "created": c.get("created", ""),
    }


def list_companies():
    rows = db.read("MATCH (c:Company) RETURN c ORDER BY c.created, c.name", None, db.META_GRAPH)
    return [_row(r) for r in rows]


def get_company(company_id):
    rows = db.read("MATCH (c:Company {id: $id}) RETURN c", {"id": company_id}, db.META_GRAPH)
    return _row(rows[0]) if rows else None


def create_company(name, admin="You"):
    base = slugify(name)
    if base in {"graphdesk-meta", "graphdesk_meta"}:
        base = base + "-co"
    company_id, n = base, 2
    while get_company(company_id):
        company_id = f"{base}-{n}"
        n += 1
    db.merge_node(
        "Company", company_id,
        {"name": name, "graph": company_id, "finished": False, "admin": admin,
         "created": db.TODAY},
        db.META_GRAPH,
    )
    db.ensure_graph(company_id)
    loader.ensure_agents(company_id)
    return get_company(company_id)


def set_finished(company_id, finished=True):
    db.write("MATCH (c:Company {id: $id}) SET c.finished = $f",
             {"id": company_id, "f": finished}, db.META_GRAPH)


def boot():
    """Make sure the meta graph and the Lumen demo company exist and are loaded."""
    db.ensure_graph(db.META_GRAPH)
    if not get_company(LUMEN):
        db.merge_node(
            "Company", LUMEN,
            {"name": "Lumen", "graph": LUMEN, "finished": True, "admin": "Maya Chen",
             "created": "2026-03-01"},
            db.META_GRAPH,
        )
    db.ensure_graph(LUMEN)
    if loader.person_count(LUMEN) == 0:
        loader.load_seed(LUMEN)
