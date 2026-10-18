"""Three department scopes for Slack bots: Engineering, Design, Sales & Marketing.

A bot assigned a department only names systems labelled with that id. The web Ask page has
no department, so it still sees the whole company graph. A question about a system outside
the bot's department is answered "I can't find a source." — the hidden system is never named.
"""
import db

CATALOG = [
    {"id": "engineering", "name": "Engineering",
     "blurb": "Services, repos and the people who ship them.",
     "try": ["Tell me who is actually on Dunning mailer", "Who owns Auth?"]},
    {"id": "design", "name": "Design",
     "blurb": "The dashboard, the design system, and the people who shape them.",
     "try": ["What did we decide about Paid stamp?", "Who owns Design system?"]},
    {"id": "sales", "name": "Sales & Marketing",
     "blurb": "The public site, pricing, and go-to-market.",
     "try": ["Remember what we already said about Quote builder?", "Who owns Marketing site?"]},
]

BY_ID = {d["id"]: d for d in CATALOG}


def known(department):
    """Return the id if it is a real department, else None (company-wide)."""
    return department if department in BY_ID else None


def context(g, department):
    """Systems and people this department's bot is allowed to name."""
    dept = known(department)
    if not dept:
        systems = db.read(
            """MATCH (s:System)
               OPTIONAL MATCH (p:Person)-[o:OWNS]->(s) WHERE o.end IS NULL
               RETURN s.id, s.name, s.department, p.name ORDER BY s.name""", None, g)
        people = db.read(
            """MATCH (p:Person)-[:MEMBER_OF]->(t:Team)
               RETURN p.id, p.name, p.role, t.name ORDER BY p.name""", None, g)
    else:
        systems = db.read(
            """MATCH (s:System {department: $d})
               OPTIONAL MATCH (p:Person)-[o:OWNS]->(s) WHERE o.end IS NULL
               RETURN s.id, s.name, s.department, p.name ORDER BY s.name""", {"d": dept}, g)
        people = db.read(
            """MATCH (p:Person)-[:MEMBER_OF]->(t:Team {department: $d})
               RETURN p.id, p.name, p.role, t.name ORDER BY p.name""", {"d": dept}, g)
    return {
        "systems": [{"id": r[0], "name": r[1], "department": r[2] or "", "owner": r[3]} for r in systems],
        "people": [{"id": r[0], "name": r[1], "role": r[2] or "", "team": r[3]} for r in people],
    }


def public(g):
    """Catalog plus live context, for the dashboard."""
    out = []
    for d in CATALOG:
        ctx = context(g, d["id"])
        out.append({**d, **ctx})
    return out
