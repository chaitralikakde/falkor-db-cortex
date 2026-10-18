"""Department-scoped Ask: a bot only names systems labelled for its department.

    docker compose exec api python test_departments.py
"""
import agents
import companies
import db
import loader
import state

G = "depttest"
NO = "I can't find a source."


def ask(q, department=None):
    s = state.settings(G, "Dept")
    return agents.ask(G, q, s, asked_by="Test", use_context=False, department=department)


def main():
    companies.boot()
    try:
        db.graph(G).delete()
    except Exception:
        pass
    loader.load_seed(G)

    # company-wide (the web Ask) still sees every system
    whole = ask("Who owns Payments API?")
    assert "Priya Shah owns Payments API" in whole["sentence"], whole["sentence"]
    web = ask("Who owns Lumen Web?")
    assert "Lena Park owns Lumen Web" in web["sentence"], web["sentence"]
    mkt = ask("Who owns Marketing site?")
    assert "Riley Cho owns Marketing site" in mkt["sentence"], mkt["sentence"]

    # Engineering bot: payments yes, design/sales no. The hidden names never appear.
    eng = ask("Who owns Payments API?", "engineering")
    assert "Priya Shah owns Payments API" in eng["sentence"], eng["sentence"]
    why = ask("Why did we decide Payments API?", "engineering")
    assert "Postgres" in why["sentence"], why["sentence"]
    for q in ("Who owns Lumen Web?", "Who owns Design system?", "Who owns Marketing site?",
              "Why did we decide Design system?"):
        r = ask(q, "engineering")
        assert r["sentence"] == NO and r["refused"], (q, r["sentence"])
        assert "Lumen Web" not in r["sentence"] and "Marketing" not in r["sentence"]
        assert "Aisha" not in r["sentence"] and "Riley" not in r["sentence"]

    # Design bot: dashboard and design system yes, payments no
    ds = ask("Who owns Design system?", "design")
    assert "Aisha Rahman owns Design system" in ds["sentence"], ds["sentence"]
    dash = ask("Who owns Lumen Web?", "design")
    assert "Lena Park owns Lumen Web" in dash["sentence"], dash["sentence"]
    fig = ask("Why did we decide Design system?", "design")
    assert "Figma" in fig["sentence"], fig["sentence"]
    pay = ask("Who owns Payments API?", "design")
    assert pay["sentence"] == NO, pay["sentence"]
    assert "Priya" not in pay["sentence"] and "Payments" not in pay["sentence"]

    # Sales bot
    sales = ask("Who owns Marketing site?", "sales")
    assert "Riley Cho owns Marketing site" in sales["sentence"], sales["sentence"]
    price = ask("Why did we decide Marketing site?", "sales")
    assert "pricing" in price["sentence"].lower(), price["sentence"]
    assert ask("Who owns Payments API?", "sales")["sentence"] == NO
    assert ask("Who owns Design system?", "sales")["sentence"] == NO

    # Slack demo questions: owner / decision / recall, one exclusive system each
    dunning = ask("Tell me who is actually on Dunning mailer", "engineering")
    assert "Sam Okonkwo owns Dunning mailer" in dunning["sentence"], dunning["sentence"]
    assert "Nobody else has authored or reviewed" in dunning["sentence"], dunning["sentence"]
    assert ask("Tell me who is actually on Dunning mailer", "design")["sentence"] == NO
    assert ask("Tell me who is actually on Dunning mailer", "sales")["sentence"] == NO

    stamp = ask("What did we decide about Paid stamp?", "design")
    assert "Paid stamp is the Figma SVG" in stamp["sentence"], stamp["sentence"]
    assert "Paid stamp is a PNG in Drive" in stamp["sentence"], stamp["sentence"]
    assert ask("What did we decide about Paid stamp?", "engineering")["sentence"] == NO
    assert ask("What did we decide about Paid stamp?", "sales")["sentence"] == NO

    quote = ask("Remember what we already said about Quote builder?", "sales")
    assert "Riley Cho owns Quote builder" in quote["sentence"], quote["sentence"]
    assert "spreadsheet" in quote["sentence"].lower(), quote["sentence"]
    assert ask("Remember what we already said about Quote builder?", "engineering")["sentence"] == NO
    assert ask("Remember what we already said about Quote builder?", "design")["sentence"] == NO

    # unknown department id behaves like company-wide
    assert "Priya" in ask("Who owns Payments API?", "not-a-dept")["sentence"]

    db.graph(G).delete()
    print("ok: three departments, no leakage of hidden systems or names")


if __name__ == "__main__":
    main()
