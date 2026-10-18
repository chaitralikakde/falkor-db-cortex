"""python -m load_seed [--reset]

Loads the Lumen seed into the `lumen` graph and runs the queries from sample-data.md.
Exits non-zero if an expected answer is wrong, so nothing gets built on a bad seed.
"""
import sys

import companies
import db
import loader


def check(label, ok, got):
    print(f"[{'ok' if ok else 'FAIL'}] {label}: {got}")
    return ok


def main():
    g = "lumen"
    companies.boot()
    if "--reset" in sys.argv:
        print("reset:", loader.reset_graph(g))
    elif loader.person_count(g) == 0:
        print("loaded:", loader.load_seed(g))
    else:
        print("lumen already has people; use --reset to rebuild")

    ok = True

    rows = db.read(
        """MATCH (s:Session)-[:RECALLS]->(n)
           WHERE s.id = 'session-1017'
           RETURN labels(n)[0] AS kind, coalesce(n.name, n.title, n.text) AS label""", None, g)
    got = sorted(r[1] for r in rows)
    ok &= check("recall session-1017", got == sorted(["Priya Shah", "Payments API", "ADR-12", "use Postgres"]), got)

    rows = db.read(
        """MATCH (p:Person)-[o:OWNS]->(s:System {name: 'Payments API'})
           WHERE o.end IS NULL RETURN p.name, o.start""", None, g)
    ok &= check("owner of Payments API", rows == [["Priya Shah", "2026-03-01"]] or
                [list(r) for r in rows] == [["Priya Shah", "2026-03-01"]], rows)

    rows = db.read(
        """MATCH (p:Person)-[a:AUTHORED|REVIEWED]->(pr:PullRequest)-[:CHANGES]->(s:System {name: 'Payments API'})
           RETURN p.name, count(DISTINCT pr) AS n ORDER BY n DESC, p.name""", None, g)
    order = [r[0] for r in rows]
    ok &= check("experts, Priya first, Jordan absent",
                order[:1] == ["Priya Shah"] and set(order[1:]) == {"Diego Alvarez", "Sam Okonkwo"}
                and "Jordan Lee" not in order, rows)

    rows = db.read(
        """MATCH (p:Person)-[:WORKS_ON]->(proj:Project)-[:USES]->(sys:System {name: 'Payments API'})
           MATCH (d:Decision {status: 'accepted'})-[:ABOUT]->(proj)
           MATCH (d)-[:WRITTEN_IN]->(doc:Doc)
           RETURN p.name, proj.name, d.text, doc.title""", None, g)
    ok &= check("people + project + decision walk",
                {r[0] for r in rows} == {"Priya Shah", "Noah Kim"}
                and all(r[2] == "use Postgres" for r in rows), rows)

    rows = db.read(
        """MATCH (d:Decision {status: 'accepted'})-[:ABOUT]->(:System {name: 'Payments API'})
           MATCH (d)-[:WRITTEN_IN|SOURCES]->(src)
           OPTIONAL MATCH (old:Decision)-[:REPLACED_BY]->(d)
           RETURN d.text, coalesce(src.name, src.title, src.key) AS source, old.text""", None, g)
    sources = {r[1] for r in rows}
    ok &= check("decision: Postgres, replaced MySQL",
                {r[0] for r in rows} == {"use Postgres"} and {r[2] for r in rows} == {"use MySQL"}
                and {"ADR-12", "LUM-18"} <= sources, sorted(sources))

    rows = db.read(
        """MATCH (s:System)
           OPTIONAL MATCH (p:Person)-[:AUTHORED]->(:PullRequest)-[:CHANGES]->(s)
           WITH s, collect(DISTINCT p.name) AS authors
           WHERE size(authors) = 1
           RETURN s.name, authors""", None, g)
    ok &= check("single-expert risk", any(r[0] == "Billing webhooks" and r[1] == ["Diego Alvarez"] for r in rows), rows)

    rows = db.read("MATCH (:Message)-[:PROPOSES]->(:System {id:'sys-pay'}) RETURN count(*)", None, g)
    ok &= check("handoff proposed, not applied", rows[0][0] == 1, rows)

    rows = db.read(
        """MATCH (s:System)
           RETURN s.department, collect(s.name) ORDER BY s.department""", None, g)
    by = {r[0]: set(r[1]) for r in rows}
    ok &= check("department labels",
                by.get("engineering") == {"Payments API", "Auth", "Billing webhooks", "Dunning mailer"}
                and by.get("design") == {"Lumen Web", "Design system", "Paid stamp"}
                and by.get("sales") == {"Marketing site", "Quote builder"}, by)

    rows = db.read(
        """MATCH (p:Person)-[o:OWNS]->(s:System)
           WHERE o.end IS NULL AND s.department IN ['design', 'sales']
           RETURN s.name, p.name ORDER BY s.name""", None, g)
    got = {r[0]: r[1] for r in rows}
    ok &= check("design and sales owners",
                got == {"Design system": "Aisha Rahman", "Lumen Web": "Lena Park",
                        "Paid stamp": "Aisha Rahman", "Marketing site": "Riley Cho",
                        "Quote builder": "Riley Cho"}, got)

    rows = db.read(
        """MATCH (p:Person)-[o:OWNS]->(s:System {name: 'Dunning mailer'})
           WHERE o.end IS NULL RETURN p.name, o.start""", None, g)
    ok &= check("Sam owns Dunning mailer",
                [list(r) for r in rows] == [["Sam Okonkwo", "2026-10-12"]], rows)

    rows = db.read(
        """MATCH (p:Person)-[:AUTHORED|REVIEWED]->(:PullRequest)-[:CHANGES]->(:System {name: 'Dunning mailer'})
           RETURN collect(DISTINCT p.name)""", None, g)
    ok &= check("Dunning mailer, Sam only", rows and set(rows[0][0]) == {"Sam Okonkwo"}, rows)

    rows = db.read(
        """MATCH (d:Decision {status: 'accepted'})-[:ABOUT]->(:System {name: 'Paid stamp'})
           OPTIONAL MATCH (old:Decision)-[:REPLACED_BY]->(d)
           RETURN d.text, old.text""", None, g)
    ok &= check("Paid stamp replaced Drive PNG",
                rows and rows[0][0] == "Paid stamp is the Figma SVG"
                and rows[0][1] == "Paid stamp is a PNG in Drive", rows)

    rows = db.read(
        """MATCH (s:Session {id: 'session-quote'})-[:RECALLS]->(n)
           RETURN s.conclusion, labels(n)[0], coalesce(n.name, n.title, n.text)""", None, g)
    labels = {r[2] for r in rows}
    ok &= check("recall session-quote",
                rows and "Riley Cho owns Quote builder" in rows[0][0]
                and {"Riley Cho", "Quote builder", "ADR-23",
                     "reseller prices come from Quote builder"} <= labels, labels)

    counts = db.read("MATCH (n) RETURN count(n)", None, g)[0][0]
    links = db.read("MATCH ()-[r]->() RETURN count(r)", None, g)[0][0]
    print(f"graph lumen: {counts} nodes, {links} links")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
