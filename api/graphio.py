"""Turn FalkorDB result cells into the JSON the canvas draws."""
from falkordb.edge import Edge
from falkordb.node import Node

import db

COLOR = {
    "Person": "#FF6B6B",
    "Team": "#4C78D4",
    "Project": "#E36AA8",
    "System": "#3DAB6E",
    "Decision": "#F5A524",
    "Repo": "#7A6FF0",
    "PullRequest": "#7A6FF0",
    "Doc": "#9AA0A6",
    "Ticket": "#9AA0A6",
    "Message": "#9AA0A6",
    "Environment": "#5FB8C9",
    "Session": "#F5C16C",
    "Finding": "#F5C16C",
    "Task": "#F5C16C",
    "Agent": "#C792EA",
}
PATH_COLOR = "#F5C16C"


def label_for(label, props):
    return props.get("name") or props.get("key") or props.get("title") or props.get("text") or props.get("id")


def node_dict(label, props):
    data = dict(props)
    data["name"] = label_for(label, data)
    return {
        "id": data["id"],
        "label": label,
        "color": COLOR.get(label, "#9AA0A6"),
        "data": data,
    }


def node_json(n):
    label = n.labels[0] if n.labels else ""
    return node_dict(label, n.properties)


def link_id(src, rel, dst):
    return f"{src}|{rel}|{dst}"


def link_dict(src, rel, dst, props=None):
    return {
        "id": link_id(src, rel, dst),
        "source": src,
        "target": dst,
        "relationship": rel,
        "data": dict(props or {}),
    }


def collect(rows):
    """Walk every cell of a result set. Returns (nodes, links) in first-seen order."""
    by_internal = {}
    edges = []

    def walk(cell):
        if cell is None:
            return
        if isinstance(cell, Node):
            by_internal.setdefault(cell.id, cell)
        elif isinstance(cell, Edge):
            edges.append(cell)
        elif isinstance(cell, (list, tuple)):
            for item in cell:
                walk(item)

    for row in rows:
        for cell in row:
            walk(cell)

    nodes, seen = [], set()
    for n in by_internal.values():
        j = node_json(n)
        if j["id"] not in seen:
            seen.add(j["id"])
            nodes.append(j)

    links, seen_links = [], set()
    for e in edges:
        a, b = by_internal.get(e.src_node), by_internal.get(e.dest_node)
        if a is None or b is None:
            continue
        j = link_dict(a.properties["id"], e.relation, b.properties["id"], e.properties)
        if j["id"] not in seen_links:
            seen_links.add(j["id"])
            links.append(j)
    return nodes, links


def export_graph(graph_name, limit=600):
    rows = db.read(
        "MATCH (a)-[r]->(b) RETURN a, r, b LIMIT $limit", {"limit": limit}, graph_name
    )
    nodes, links = collect(rows)
    # nodes with no links at all (e.g. a fresh Doc) still belong on the map
    iso = db.read("MATCH (n) WHERE NOT (n)--() RETURN n LIMIT $limit", {"limit": limit}, graph_name)
    known = {n["id"] for n in nodes}
    for row in iso:
        j = node_json(row[0])
        if j["id"] not in known:
            nodes.append(j)
    return {"nodes": nodes, "links": links}


def bundle_to_graph(bundle):
    """Render a bundle (nodes/links just written) in the canvas shape."""
    nodes = [node_dict(n["label"], {"id": n["id"], **n["props"]}) for n in bundle["nodes"]]
    links = [link_dict(l["src"][1], l["rel"], l["dst"][1], l.get("props")) for l in bundle["links"]]
    return {"nodes": nodes, "links": links}
