"""One loader for everything that writes company context: seed, upload, form, connectors."""
import db
import lumen_seed

AGENTS = [
    {"label": "Agent", "id": "agent-mapper",
     "props": {"name": "Mapper", "summary": "Runs the Cypher tools and writes a Finding", "source": "system"}},
    {"label": "Agent", "id": "agent-clerk",
     "props": {"name": "Clerk", "summary": "Reads the Finding, proposes handoffs, phrases the answer",
               "source": "system"}},
]


def load_bundle(bundle, graph_name):
    """Nodes first, then links, one MERGE per node and per link."""
    for n in bundle["nodes"]:
        db.merge_node(n["label"], n["id"], n["props"], graph_name)
    for l in bundle["links"]:
        db.merge_link(l["src"][0], l["src"][1], l["rel"], l["dst"][0], l["dst"][1],
                      l.get("props"), graph_name)
    return {"nodes": len(bundle["nodes"]), "links": len(bundle["links"])}


def ensure_agents(graph_name):
    load_bundle({"nodes": AGENTS, "links": []}, graph_name)


def person_count(graph_name):
    rows = db.read("MATCH (p:Person) RETURN count(p)", None, graph_name)
    return rows[0][0] if rows else 0


def load_seed(graph_name="lumen"):
    db.ensure_graph(graph_name)
    return load_bundle(lumen_seed.build(), graph_name)


def reset_graph(graph_name):
    """Delete the graph and rebuild it (used by Reset demo for Lumen)."""
    try:
        db.graph(graph_name).delete()
    except Exception:
        pass
    return load_seed(graph_name)
