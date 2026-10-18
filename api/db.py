import os
import time

from falkordb import FalkorDB

GRAPH_NAME = "lumen"
META_GRAPH = "graphdesk_meta"
TODAY = os.environ.get("GRAPH_TODAY", "2026-10-18")

# Fixed allow-lists. Labels and relationship types are never taken from user text.
LABELS = {
    "Person", "Team", "Project", "System", "Repo", "PullRequest", "Ticket",
    "Message", "Doc", "Decision", "Environment", "Session", "Finding", "Task",
    "Agent", "Company",
}
RELS = {
    "MEMBER_OF", "WORKS_ON", "USES", "OWNS", "AUTHORED", "REVIEWED", "CHANGES",
    "ABOUT", "DECIDES", "WRITTEN_IN", "SOURCES", "PROPOSES", "RUNS_IN",
    "REPLACED_BY", "RECALLS", "FOUND", "ASSIGNS", "ASKED_BY", "RAN", "WROTE",
    "PART_OF",
}

_client = None


def client():
    global _client
    if _client is None:
        _client = FalkorDB(
            host=os.environ.get("FALKORDB_HOST", "localhost"),
            port=int(os.environ.get("FALKORDB_PORT", "6379")),
        )
    return _client


def graph(name=GRAPH_NAME):
    return client().select_graph(name)


def _missing_graph(err):
    msg = str(err).lower()
    return "empty key" in msg or "invalid graph" in msg


def write(cypher, params=None, name=GRAPH_NAME):
    """GRAPH.QUERY: may write."""
    return graph(name).query(cypher, params or {})


def read_full(cypher, params=None, name=GRAPH_NAME):
    """GRAPH.RO_QUERY: errors if the Cypher writes. Returns (rows, ms)."""
    started = time.perf_counter()
    try:
        res = graph(name).ro_query(cypher, params or {})
    except Exception as err:  # graph does not exist yet
        if _missing_graph(err):
            return [], 0.0
        raise
    wall = (time.perf_counter() - started) * 1000
    ms = getattr(res, "run_time_ms", None)
    return res.result_set, round(float(ms) if ms else wall, 2)


def read(cypher, params=None, name=GRAPH_NAME):
    return read_full(cypher, params, name)[0]


def ensure_graph(name):
    """Create the graph (and an id index per label) so reads never hit a missing key."""
    for label in sorted(LABELS):
        try:
            write(f"CREATE INDEX FOR (n:{label}) ON (n.id)", None, name)
        except Exception as err:
            if "already indexed" in str(err).lower() or "already exists" in str(err).lower():
                continue
            raise


def merge_node(label, node_id, props, name=GRAPH_NAME):
    if label not in LABELS:
        raise ValueError(f"unknown label: {label}")
    write(
        f"""MERGE (n:{label} {{id: $id}})
            ON CREATE SET n += $props
            ON MATCH SET n += $props""",
        {"id": node_id, "props": props},
        name,
    )


def merge_link(src_label, src_id, rel, dst_label, dst_id, props=None, name=GRAPH_NAME):
    if src_label not in LABELS or dst_label not in LABELS:
        raise ValueError("unknown label")
    if rel not in RELS:
        raise ValueError(f"unknown relationship: {rel}")
    write(
        f"""MATCH (a:{src_label} {{id: $src}})
            MATCH (b:{dst_label} {{id: $dst}})
            MERGE (a)-[r:{rel}]->(b)
            SET r += $props""",
        {"src": src_id, "dst": dst_id, "props": props or {}},
        name,
    )
