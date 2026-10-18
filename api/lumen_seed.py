"""The Lumen demo company as a bundle: {"nodes": [...], "links": [...]}.

Same shape the upload extractor produces, so the seed and an admin upload
go through one loader (loader.load_bundle).
"""

TODAY = "2026-10-18"


def build():
    nodes, links = [], []

    def N(label, node_id, name, **props):
        nodes.append({"label": label, "id": node_id,
                      "props": {"name": name, "source": "seed", **props}})

    def L(src, rel, dst, **props):
        links.append({"src": list(src), "rel": rel, "dst": list(dst), "props": props})

    # ---- 1. Teams, people, MEMBER_OF ------------------------------------
    # department is the Slack-bot scope: a bot assigned that id only names these teams' systems.
    teams = [("team-product", "Product", None), ("team-eng", "Engineering", "engineering"),
             ("team-design", "Design", "design"), ("team-sales", "Sales & Marketing", "sales"),
             ("team-success", "Success", None)]
    for tid, name, dept in teams:
        props = {"department": dept} if dept else {}
        N("Team", tid, name, **props)

    # id, name, role, team, github, slack, linear
    people = [
        ("maya", "Maya Chen", "CEO", "team-product", "maya-chen", "U_MAYA", None),
        ("noah", "Noah Kim", "PM", "team-product", "noah-kim", "U_NOAH", "noah"),
        ("aisha", "Aisha Rahman", "Design lead", "team-design", "aisha-rahman", "U_AISHA", None),
        ("riley", "Riley Cho", "Marketing lead", "team-sales", "riley-cho", "U_RILEY", None),
        ("priya", "Priya Shah", "Eng lead", "team-eng", "priya-shah", "U_PRIYA", "priya"),
        ("sam", "Sam Okonkwo", "Backend", "team-eng", "sam-okonkwo", "U_SAM", "sam"),
        ("lena", "Lena Park", "Frontend", "team-eng", "lena-park", "U_LENA", "lena"),
        ("diego", "Diego Alvarez", "Infra", "team-eng", "diego-alvarez", "U_DIEGO", "diego"),
        ("jordan", "Jordan Lee", "New hire, started 2026-10-13", "team-eng",
         "jordan-lee", "U_JORDAN", "jordan"),
        ("chris", "Chris Doyle", "Support", "team-success", "chris-doyle", "U_CHRIS", "chris"),
    ]
    for pid, name, role, team, gh, slack, linear in people:
        props = {"email": f"{pid}@lumen.example", "github": gh, "slack": slack,
                 "role": role, "url": f"https://github.com/{gh}"}
        if linear:
            props["linear"] = linear
        N("Person", pid, name, **props)
        L(("Person", pid), "MEMBER_OF", ("Team", team))

    # ---- 2. Environments, systems, projects, repos ----------------------
    N("Environment", "env-prod", "prod")
    N("Environment", "env-staging", "staging")

    N("Repo", "repo-api", "lumen-api", url="https://github.com/lumen-hq/lumen-api")
    N("Repo", "repo-web", "lumen-web", url="https://github.com/lumen-hq/lumen-web")

    # id, name, summary, repo or None, envs, department
    systems = [
        ("sys-web", "Lumen Web", "Freelancer dashboard", "repo-web", ["env-prod"], "design"),
        ("sys-ds", "Design system", "Tokens, components, Figma source of truth", "repo-web",
         ["env-prod"], "design"),
        ("sys-pay", "Payments API", "Charges and invoices", "repo-api", ["env-prod", "env-staging"],
         "engineering"),
        ("sys-auth", "Auth", "Login and session tokens", "repo-api", ["env-prod", "env-staging"],
         "engineering"),
        ("sys-hooks", "Billing webhooks", "Stripe event intake and retries", "repo-api",
         ["env-prod", "env-staging"], "engineering"),
        ("sys-dunning", "Dunning mailer",
         "Failed-invoice nags, sent from Lumen after Mailchimp double-charged two freelancers",
         "repo-api", ["env-prod", "env-staging"], "engineering"),
        ("sys-stamp", "Paid stamp",
         "Green Paid mark on invoices; Figma SVG is the legal source", "repo-web",
         ["env-prod"], "design"),
        ("sys-mkt", "Marketing site", "Public pricing and signup", None, ["env-prod"], "sales"),
        ("sys-quote", "Quote builder",
         "Locked partner rate card; not Riley's spreadsheet", None, ["env-prod"], "sales"),
    ]
    repo_name = {"repo-api": "lumen-api", "repo-web": "lumen-web"}
    repo_id = {v: k for k, v in repo_name.items()}
    for sid, name, summary, repo, envs, dept in systems:
        url = f"https://github.com/lumen-hq/{repo_name[repo]}" if repo else "https://lumen.example"
        N("System", sid, name, summary=summary, department=dept, url=url)
        if repo:
            L(("System", sid), "PART_OF", ("Repo", repo))
        for env in envs:
            L(("System", sid), "RUNS_IN", ("Environment", env))

    N("Project", "proj-migration", "Payments database migration")
    N("Project", "proj-hooks", "Webhook reliability")
    N("Project", "proj-failed", "Failed invoices on the dashboard")
    N("Project", "proj-ds", "Design system launch")
    N("Project", "proj-pricing", "Public pricing page")
    N("Project", "proj-dunning", "Take dunning off Mailchimp")
    N("Project", "proj-stamp", "Paid stamp in Figma")
    N("Project", "proj-quote", "Lock partner prices")
    L(("Project", "proj-migration"), "USES", ("System", "sys-pay"))
    L(("Project", "proj-hooks"), "USES", ("System", "sys-hooks"))
    L(("Project", "proj-failed"), "USES", ("System", "sys-web"))
    L(("Project", "proj-ds"), "USES", ("System", "sys-ds"))
    L(("Project", "proj-pricing"), "USES", ("System", "sys-mkt"))
    L(("Project", "proj-dunning"), "USES", ("System", "sys-dunning"))
    L(("Project", "proj-stamp"), "USES", ("System", "sys-stamp"))
    L(("Project", "proj-quote"), "USES", ("System", "sys-quote"))
    for who, proj, since in [
        ("priya", "proj-migration", "2026-06-01"), ("noah", "proj-migration", "2026-05-20"),
        ("diego", "proj-hooks", "2026-10-15"), ("lena", "proj-failed", "2026-10-01"),
        ("chris", "proj-failed", "2026-10-13"), ("aisha", "proj-failed", "2026-10-02"),
        ("aisha", "proj-ds", "2026-09-01"), ("riley", "proj-pricing", "2026-09-15"),
        ("sam", "proj-dunning", "2026-10-12"), ("aisha", "proj-stamp", "2026-10-06"),
        ("lena", "proj-stamp", "2026-10-06"), ("riley", "proj-quote", "2026-10-04"),
        ("noah", "proj-quote", "2026-10-04"),
    ]:
        L(("Person", who), "WORKS_ON", ("Project", proj), since=since)

    # ---- 3. OWNS: current owners. Sam has Dunning mailer; Payments still waits on Apply ----
    for who, sid, start in [
        ("priya", "sys-pay", "2026-03-01"), ("lena", "sys-web", "2026-01-15"),
        ("diego", "sys-auth", "2025-11-02"), ("diego", "sys-hooks", "2026-02-01"),
        ("aisha", "sys-ds", "2026-09-01"), ("riley", "sys-mkt", "2026-09-15"),
        ("sam", "sys-dunning", "2026-10-12"), ("aisha", "sys-stamp", "2026-10-08"),
        ("riley", "sys-quote", "2026-10-05"),
    ]:
        L(("Person", who), "OWNS", ("System", sid), start=start)
    # Lena put the Paid stamp PNG in Drive; legal moved it to Aisha on 8 Oct
    L(("Person", "lena"), "OWNS", ("System", "sys-stamp"), start="2026-09-01", end="2026-10-08")

    # ---- 4. Pull requests: AUTHORED, REVIEWED, CHANGES -------------------
    # id, number, title, author, reviewer, system, state, date, commits, repo
    prs = [
        ("pr-41", 41, "Stop the invoice charge timeout", "priya", "diego", "sys-pay", "merged", "2026-04-02", 8, "lumen-api"),
        ("pr-42", 42, "Split refunds out of the charge handler", "priya", "sam", "sys-pay", "merged", "2026-09-28", 10, "lumen-api"),
        ("pr-44", 44, "Move the payments store to Postgres", "priya", "diego", "sys-pay", "merged", "2026-06-19", 10, "lumen-api"),
        ("pr-47", 47, "Retry Stripe webhooks with backoff", "diego", "priya", "sys-hooks", "merged", "2026-08-04", 6, "lumen-api"),
        ("pr-51", 51, "Read the payments timeout metric", "sam", "priya", "sys-pay", "open", "2026-10-16", 2, "lumen-api"),
        ("pr-18", 18, "Invoice table and filters", "lena", "aisha", "sys-web", "merged", "2026-05-11", 4, "lumen-web"),
        ("pr-22", 22, "Show failed invoices on the dashboard", "lena", "noah", "sys-web", "merged", "2026-07-08", 3, "lumen-web"),
        ("pr-23", 23, "Fix the README install line", "jordan", "lena", "sys-web", "open", "2026-10-17", 1, "lumen-web"),
        ("pr-30", 30, "Ship design tokens from Figma", "aisha", "lena", "sys-ds", "merged", "2026-09-20", 5, "lumen-web"),
        ("pr-55", 55, "Send dunning from Lumen, not Mailchimp", "sam", None, "sys-dunning",
         "merged", "2026-10-12", 7, "lumen-api"),
        ("pr-32", 32, "Replace Drive PNG with Paid stamp SVG", "lena", "aisha", "sys-stamp",
         "merged", "2026-10-08", 3, "lumen-web"),
        ("pr-60", 60, "Kill the partner discount spreadsheet", "noah", "riley", "sys-quote",
         "merged", "2026-10-05", 2, "lumen-web"),
    ]
    for pid, num, title, author, reviewer, sid, state, date, commits, repo in prs:
        N("PullRequest", pid, f"PR {num}", number=num, title=title, state=state, date=date,
          url=f"https://github.com/lumen-hq/{repo}/pull/{num}")
        L(("PullRequest", pid), "PART_OF", ("Repo", repo_id[repo]))
        L(("PullRequest", pid), "CHANGES", ("System", sid))
        L(("Person", author), "AUTHORED", ("PullRequest", pid), commits=commits)
        if reviewer:
            L(("Person", reviewer), "REVIEWED", ("PullRequest", pid))

    # ---- 5. Tickets (Linear-shaped) and their comments -------------------
    # id, key, title, assignee, status, system, opened
    tickets = [
        ("t-12", "LUM-12", "Payments API keeps timing out on invoices", "priya", "done", "sys-pay", "2026-03-20"),
        ("t-18", "LUM-18", "Move payments database to Postgres", "priya", "done", "sys-pay", "2026-06-01"),
        ("t-19", "LUM-19", "Stay on MySQL for payments", "noah", "canceled", "sys-pay", "2026-05-20"),
        ("t-31", "LUM-31", "Dashboard empty state", "lena", "in progress", "sys-web", "2026-10-01"),
        ("t-40", "LUM-40", "Stripe webhook retries failing", "diego", "in progress", "sys-hooks", "2026-10-15"),
        ("t-44", "LUM-44", "Sam takes over Payments API", "sam", "in progress", "sys-pay", "2026-10-18"),
        ("t-45", "LUM-45", "Jordan laptop setup", "jordan", "done", None, "2026-10-13"),
        ("t-50", "LUM-50", "Customers cannot see failed invoices", "chris", "triage", "sys-web", "2026-10-13"),
        ("t-60", "LUM-60", "Publish the design system from Figma", "aisha", "done", "sys-ds", "2026-09-01"),
        ("t-70", "LUM-70", "Put pricing on the marketing site", "riley", "done", "sys-mkt", "2026-09-15"),
        ("t-81", "LUM-81", "Take Dunning mailer off Mailchimp", "sam", "done", "sys-dunning", "2026-10-11"),
        ("t-82", "LUM-82", "Paid stamp failed contrast; move to Figma", "aisha", "done", "sys-stamp",
         "2026-10-06"),
        ("t-83", "LUM-83", "Lock partner prices in Quote builder", "riley", "done", "sys-quote", "2026-10-04"),
    ]
    for tid, key, title, assignee, status, sid, opened in tickets:
        N("Ticket", tid, key, key=key, title=title, status=status, opened=opened,
          url=f"https://linear.app/lumen/issue/{key}")
        L(("Ticket", tid), "ASSIGNS", ("Person", assignee))
        if sid:
            L(("Ticket", tid), "ABOUT", ("System", sid))

    # ticket, author, date, text
    comments = [
        ("t-12", "priya", "2026-04-02", "Timeouts stopped after PR 41. Leaving this closed."),
        ("t-18", "priya", "2026-06-19", "ADR-12 is accepted. This ticket is the implementation. PR 44 merged."),
        ("t-19", "noah", "2026-06-20", "Canceling. We are not staying on MySQL. ADR-12 replaces this."),
        ("t-31", "aisha", "2026-10-02", "Empty state copy is in the design file. Lena is building it."),
        ("t-40", "diego", "2026-10-16", "Retries still fail on the second Stripe attempt. I am the only person who has changed this code."),
        ("t-44", "noah", "2026-10-18", "Priya is moving off payments. Sam owns Payments API starting today. Do not close Priya's history."),
        ("t-45", "maya", "2026-10-13", "Jordan started today. Laptop only. No production access."),
        ("t-50", "chris", "2026-10-13", "Three customers cannot see a failed invoice on the dashboard."),
        ("t-60", "aisha", "2026-09-20", "Tokens are in Figma. PR 30 shipped them. Design system is the source of truth."),
        ("t-70", "riley", "2026-09-22", "Pricing is public on the marketing site. Sales quotes the page, not a spreadsheet."),
        ("t-81", "sam", "2026-10-12",
         "Mailchimp delayed the dunning run 11 hours. Two freelancers were charged twice. "
         "Dunning mailer now sends from Lumen. I am the only person who has changed this code."),
        ("t-82", "aisha", "2026-10-08",
         "Legal pulled Lena's Drive PNG. Contrast failed. Paid stamp is the Figma SVG. ADR-22. PR 32."),
        ("t-83", "riley", "2026-10-05",
         "A Berlin partner invented 20 percent off. Partner prices come from Quote builder, not my sheet. PR 60."),
    ]
    tkey = {t[0]: t[1] for t in tickets}
    for tid, who, date, text in comments:
        cid = f"c-{tkey[tid]}"
        N("Message", cid, f"{tkey[tid]} comment", text=text, at=date, channel="linear",
          url=f"https://linear.app/lumen/issue/{tkey[tid]}#comment")
        L(("Person", who), "AUTHORED", ("Message", cid))
        L(("Message", cid), "ABOUT", ("Ticket", tid))

    # ---- 6. Docs, decisions: DECIDES, WRITTEN_IN, SOURCES, REPLACED_BY ---
    docs = [
        ("doc-12", "ADR-12", "ADR-12: Payments uses Postgres", "priya", "2026-06-18", "accepted",
         "https://lumen.example/docs/adr-12",
         "Payments API moves from MySQL to Postgres. Priya Shah owns the migration. PR 44 is the change. "
         "LUM-18 tracks the work. LUM-19, which said to stay on MySQL, is canceled and replaced by this note."),
        ("doc-04", "ADR-04", "ADR-04: Auth uses short-lived tokens", "diego", "2025-11-02", "accepted",
         "https://lumen.example/docs/adr-04",
         "Auth issues short-lived session tokens. Diego Alvarez owns Auth. No second system is involved."),
        ("doc-onboard", "Jordan started Monday", "Jordan started Monday", "maya", "2026-10-13", "note",
         "https://lumen.example/docs/onboarding-jordan",
         "Jordan Lee started on 13 October 2026. He is on Engineering. He has a laptop ticket, LUM-45, "
         "and no system access."),
        ("doc-20", "ADR-20", "ADR-20: Design system lives in Figma", "aisha", "2026-09-18", "accepted",
         "https://lumen.example/docs/adr-20",
         "The design system is the source of truth, in Figma. Aisha Rahman owns it. PR 30 ships the tokens. "
         "LUM-60 tracks the work."),
        ("doc-pricing", "Pricing is public", "Pricing is public on the marketing site", "riley", "2026-09-22",
         "accepted", "https://lumen.example/docs/pricing",
         "The marketing site publishes list pricing. Riley Cho owns the marketing site. Sales quotes that page. "
         "LUM-70 tracks the work."),
        ("doc-21", "ADR-21", "ADR-21: Dunning mailer sends from Lumen", "sam", "2026-10-12", "accepted",
         "https://lumen.example/docs/adr-21",
         "Dunning mailer sends from Lumen, not Mailchimp. Mailchimp delayed a failed-invoice run by 11 hours "
         "and two freelancers were charged twice. Sam Okonkwo owns Dunning mailer. PR 55 is the change. "
         "LUM-81 tracks the work."),
        ("doc-22", "ADR-22", "ADR-22: Paid stamp is the Figma SVG", "aisha", "2026-10-07", "accepted",
         "https://lumen.example/docs/adr-22",
         "Paid stamp is the Figma SVG. The Drive PNG failed contrast for colour-blind clients and legal pulled it. "
         "Aisha Rahman owns Paid stamp. Lena Park authored PR 32. LUM-82 tracks the work."),
        ("doc-23", "ADR-23", "ADR-23: Partner prices come from Quote builder", "riley", "2026-10-05",
         "accepted", "https://lumen.example/docs/adr-23",
         "Reseller prices come from Quote builder, not Riley's spreadsheet. A Berlin partner invented 20 percent off. "
         "Riley Cho owns Quote builder. Noah Kim authored PR 60. LUM-83 tracks the work."),
    ]
    for did, name, title, author, date, status, url, body in docs:
        N("Doc", did, name, title=title, date=date, status=status, url=url, body=body)
        L(("Person", author), "AUTHORED", ("Doc", did))

    # Slack messages
    # id, channel, who, at, text, [(label, id)]
    messages = [
        ("msg-handoff", "#eng", "noah", "2026-10-18 16:10",
         "Priya is moving off payments. Sam owns it starting today. Ticket is LUM-44.",
         [("System", "sys-pay"), ("Ticket", "t-44")]),
        ("msg-pg", "#eng", "priya", "2026-10-14 11:05",
         "ADR-12 is accepted. Payments uses Postgres.",
         [("System", "sys-pay"), ("Doc", "doc-12")]),
        ("msg-hooks", "#incidents", "diego", "2026-10-17 09:40",
         "Webhook retries are still failing. I am the only one in this code.",
         [("Ticket", "t-40"), ("System", "sys-hooks")]),
        ("msg-failed", "#support", "chris", "2026-10-13 15:02",
         "Three customers cannot see a failed invoice.",
         [("Ticket", "t-50"), ("System", "sys-web")]),
        ("msg-ds", "#design", "aisha", "2026-09-20 14:00",
         "ADR-20 is accepted. The design system lives in Figma. Tokens shipped in PR 30.",
         [("System", "sys-ds"), ("Doc", "doc-20")]),
        ("msg-pricing", "#sales", "riley", "2026-09-22 11:30",
         "Pricing is public on the marketing site. Quote the page, not the old spreadsheet.",
         [("System", "sys-mkt"), ("Doc", "doc-pricing")]),
        ("msg-dunning", "#eng", "sam", "2026-10-12 10:15",
         "Mailchimp delayed dunning 11 hours. Two freelancers were charged twice. "
         "Dunning mailer now sends from Lumen. I am the only one in this code. LUM-81.",
         [("System", "sys-dunning"), ("Ticket", "t-81"), ("Doc", "doc-21")]),
        ("msg-stamp", "#design", "aisha", "2026-10-08 13:20",
         "Legal pulled the Drive PNG. Paid stamp is the Figma SVG. ADR-22. PR 32.",
         [("System", "sys-stamp"), ("Doc", "doc-22"), ("PullRequest", "pr-32")]),
        ("msg-quote", "#sales", "riley", "2026-10-05 09:50",
         "Berlin partner invented 20 percent off. Quote builder is the only rate card. LUM-83.",
         [("System", "sys-quote"), ("Ticket", "t-83"), ("Doc", "doc-23")]),
    ]
    pname = {p[0]: p[1] for p in people}
    chan_id = {"#eng": "C_ENG", "#incidents": "C_INCIDENTS", "#support": "C_SUPPORT",
               "#design": "C_DESIGN", "#sales": "C_SALES"}
    for mid, chan, who, at, text, abouts in messages:
        N("Message", mid, f"{chan} · {pname[who]}", text=text, at=at, channel=chan,
          url=f"https://lumen.slack.com/archives/{chan_id[chan]}/{mid}")
        L(("Person", who), "AUTHORED", ("Message", mid))
        for target in abouts:
            L(("Message", mid), "ABOUT", target)

    N("Decision", "decision-postgres", "use Postgres", text="use Postgres", status="accepted",
      date="2026-06-18", url="https://lumen.example/docs/adr-12")
    N("Decision", "decision-mysql", "use MySQL", text="use MySQL", status="canceled",
      date="2026-05-20", url="https://linear.app/lumen/issue/LUM-19")
    N("Decision", "decision-tokens", "short-lived session tokens", text="short-lived session tokens",
      status="accepted", date="2025-11-02", url="https://lumen.example/docs/adr-04")
    N("Decision", "decision-figma", "Figma is the source of truth", text="Figma is the source of truth",
      status="accepted", date="2026-09-18", url="https://lumen.example/docs/adr-20")
    N("Decision", "decision-pricing", "publish pricing on the marketing site",
      text="publish pricing on the marketing site", status="accepted", date="2026-09-22",
      url="https://lumen.example/docs/pricing")
    N("Decision", "decision-dunning", "dunning sends from Lumen, not Mailchimp",
      text="dunning sends from Lumen, not Mailchimp", status="accepted", date="2026-10-12",
      url="https://lumen.example/docs/adr-21")
    N("Decision", "decision-mailchimp", "dunning goes through Mailchimp",
      text="dunning goes through Mailchimp", status="canceled", date="2026-09-01",
      url="https://linear.app/lumen/issue/LUM-81")
    N("Decision", "decision-stamp", "Paid stamp is the Figma SVG",
      text="Paid stamp is the Figma SVG", status="accepted", date="2026-10-07",
      url="https://lumen.example/docs/adr-22")
    N("Decision", "decision-png", "Paid stamp is a PNG in Drive",
      text="Paid stamp is a PNG in Drive", status="canceled", date="2026-09-01",
      url="https://linear.app/lumen/issue/LUM-82")
    N("Decision", "decision-quote", "reseller prices come from Quote builder",
      text="reseller prices come from Quote builder", status="accepted", date="2026-10-05",
      url="https://lumen.example/docs/adr-23")
    N("Decision", "decision-sheet", "quote from the sales spreadsheet",
      text="quote from the sales spreadsheet", status="canceled", date="2026-08-01",
      url="https://linear.app/lumen/issue/LUM-83")

    L(("Person", "priya"), "DECIDES", ("Decision", "decision-postgres"))
    L(("Person", "noah"), "DECIDES", ("Decision", "decision-mysql"))
    L(("Person", "diego"), "DECIDES", ("Decision", "decision-tokens"))
    L(("Person", "aisha"), "DECIDES", ("Decision", "decision-figma"))
    L(("Person", "riley"), "DECIDES", ("Decision", "decision-pricing"))
    L(("Person", "sam"), "DECIDES", ("Decision", "decision-dunning"))
    L(("Person", "aisha"), "DECIDES", ("Decision", "decision-stamp"))
    L(("Person", "lena"), "DECIDES", ("Decision", "decision-png"))
    L(("Person", "riley"), "DECIDES", ("Decision", "decision-quote"))
    L(("Person", "riley"), "DECIDES", ("Decision", "decision-sheet"))
    L(("Decision", "decision-postgres"), "ABOUT", ("System", "sys-pay"))
    L(("Decision", "decision-postgres"), "ABOUT", ("Project", "proj-migration"))
    L(("Decision", "decision-mysql"), "ABOUT", ("System", "sys-pay"))
    L(("Decision", "decision-tokens"), "ABOUT", ("System", "sys-auth"))
    L(("Decision", "decision-figma"), "ABOUT", ("System", "sys-ds"))
    L(("Decision", "decision-figma"), "ABOUT", ("Project", "proj-ds"))
    L(("Decision", "decision-pricing"), "ABOUT", ("System", "sys-mkt"))
    L(("Decision", "decision-pricing"), "ABOUT", ("Project", "proj-pricing"))
    L(("Decision", "decision-dunning"), "ABOUT", ("System", "sys-dunning"))
    L(("Decision", "decision-dunning"), "ABOUT", ("Project", "proj-dunning"))
    L(("Decision", "decision-mailchimp"), "ABOUT", ("System", "sys-dunning"))
    L(("Decision", "decision-stamp"), "ABOUT", ("System", "sys-stamp"))
    L(("Decision", "decision-stamp"), "ABOUT", ("Project", "proj-stamp"))
    L(("Decision", "decision-png"), "ABOUT", ("System", "sys-stamp"))
    L(("Decision", "decision-quote"), "ABOUT", ("System", "sys-quote"))
    L(("Decision", "decision-quote"), "ABOUT", ("Project", "proj-quote"))
    L(("Decision", "decision-sheet"), "ABOUT", ("System", "sys-quote"))
    L(("Decision", "decision-postgres"), "WRITTEN_IN", ("Doc", "doc-12"))
    L(("Decision", "decision-mysql"), "WRITTEN_IN", ("Ticket", "t-19"))
    L(("Decision", "decision-tokens"), "WRITTEN_IN", ("Doc", "doc-04"))
    L(("Decision", "decision-figma"), "WRITTEN_IN", ("Doc", "doc-20"))
    L(("Decision", "decision-pricing"), "WRITTEN_IN", ("Doc", "doc-pricing"))
    L(("Decision", "decision-dunning"), "WRITTEN_IN", ("Doc", "doc-21"))
    L(("Decision", "decision-mailchimp"), "WRITTEN_IN", ("Ticket", "t-81"))
    L(("Decision", "decision-stamp"), "WRITTEN_IN", ("Doc", "doc-22"))
    L(("Decision", "decision-png"), "WRITTEN_IN", ("Ticket", "t-82"))
    L(("Decision", "decision-quote"), "WRITTEN_IN", ("Doc", "doc-23"))
    L(("Decision", "decision-sheet"), "WRITTEN_IN", ("Ticket", "t-83"))
    L(("Decision", "decision-postgres"), "SOURCES", ("Ticket", "t-18"))
    L(("Decision", "decision-postgres"), "SOURCES", ("PullRequest", "pr-44"))
    L(("Decision", "decision-postgres"), "SOURCES", ("Message", "msg-pg"))
    L(("Decision", "decision-mysql"), "SOURCES", ("Ticket", "t-19"))
    L(("Decision", "decision-tokens"), "SOURCES", ("Doc", "doc-04"))
    L(("Decision", "decision-figma"), "SOURCES", ("Ticket", "t-60"))
    L(("Decision", "decision-figma"), "SOURCES", ("PullRequest", "pr-30"))
    L(("Decision", "decision-figma"), "SOURCES", ("Message", "msg-ds"))
    L(("Decision", "decision-pricing"), "SOURCES", ("Ticket", "t-70"))
    L(("Decision", "decision-pricing"), "SOURCES", ("Message", "msg-pricing"))
    L(("Decision", "decision-dunning"), "SOURCES", ("Ticket", "t-81"))
    L(("Decision", "decision-dunning"), "SOURCES", ("PullRequest", "pr-55"))
    L(("Decision", "decision-dunning"), "SOURCES", ("Message", "msg-dunning"))
    L(("Decision", "decision-mailchimp"), "SOURCES", ("Ticket", "t-81"))
    L(("Decision", "decision-stamp"), "SOURCES", ("Ticket", "t-82"))
    L(("Decision", "decision-stamp"), "SOURCES", ("PullRequest", "pr-32"))
    L(("Decision", "decision-stamp"), "SOURCES", ("Message", "msg-stamp"))
    L(("Decision", "decision-png"), "SOURCES", ("Ticket", "t-82"))
    L(("Decision", "decision-quote"), "SOURCES", ("Ticket", "t-83"))
    L(("Decision", "decision-quote"), "SOURCES", ("PullRequest", "pr-60"))
    L(("Decision", "decision-quote"), "SOURCES", ("Message", "msg-quote"))
    L(("Decision", "decision-sheet"), "SOURCES", ("Ticket", "t-83"))
    L(("Decision", "decision-mysql"), "REPLACED_BY", ("Decision", "decision-postgres"))
    L(("Decision", "decision-mailchimp"), "REPLACED_BY", ("Decision", "decision-dunning"))
    L(("Decision", "decision-png"), "REPLACED_BY", ("Decision", "decision-stamp"))
    L(("Decision", "decision-sheet"), "REPLACED_BY", ("Decision", "decision-quote"))

    # ---- 7. Proposed, not applied ----------------------------------------
    for src in [("Message", "msg-handoff"), ("Ticket", "t-44")]:
        L(src, "PROPOSES", ("System", "sys-pay"), start=TODAY, owner="sam", system="sys-pay")

    # ---- 8. Agents, session-1017, finding, task-handoff -------------------
    N("Agent", "agent-mapper", "Mapper", summary="Runs the Cypher tools and writes a Finding")
    N("Agent", "agent-clerk", "Clerk", summary="Reads the Finding, proposes handoffs, phrases the answer")

    N("Session", "session-1017", "session-1017",
      question="Who owns Payments API, and why Postgres?", at="2026-10-17T18:00",
      asked_by="Maya Chen",
      conclusion="Priya Shah since 2026-03-01. Postgres is accepted in ADR-12.")
    L(("Session", "session-1017"), "ASKED_BY", ("Person", "maya"))
    L(("Session", "session-1017"), "RAN", ("Agent", "agent-mapper"))
    for label, nid in [("Person", "priya"), ("System", "sys-pay"),
                       ("Decision", "decision-postgres"), ("Doc", "doc-12")]:
        L(("Session", "session-1017"), "RECALLS", (label, nid))

    N("Finding", "finding-1017", "finding-1017", tool="find_owner,find_decision",
      body="Maya asked. Mapper ran find_owner and find_decision. Rows: Priya Shah, Payments API, ADR-12, LUM-18.")
    L(("Finding", "finding-1017"), "FOUND", ("Session", "session-1017"))
    for label, nid in [("Person", "priya"), ("System", "sys-pay"), ("Doc", "doc-12")]:
        L(("Finding", "finding-1017"), "FOUND", (label, nid))

    N("Session", "session-quote", "session-quote",
      question="Who sets partner prices, Quote builder or the spreadsheet?", at="2026-10-17T16:40",
      asked_by="Maya Chen",
      conclusion="Riley Cho owns Quote builder; partner prices do not come from the spreadsheet.")
    L(("Session", "session-quote"), "ASKED_BY", ("Person", "maya"))
    L(("Session", "session-quote"), "RAN", ("Agent", "agent-mapper"))
    for label, nid in [("Person", "riley"), ("System", "sys-quote"),
                       ("Decision", "decision-quote"), ("Doc", "doc-23")]:
        L(("Session", "session-quote"), "RECALLS", (label, nid))

    N("Finding", "finding-quote", "finding-quote", tool="recall_session",
      body="Maya asked. Mapper ran recall_session. Rows: Riley Cho, Quote builder, ADR-23.")
    L(("Finding", "finding-quote"), "FOUND", ("Session", "session-quote"))
    for label, nid in [("Person", "riley"), ("System", "sys-quote"), ("Doc", "doc-23")]:
        L(("Finding", "finding-quote"), "FOUND", (label, nid))

    N("Task", "task-handoff", "Confirm Sam as payments owner",
      title="Confirm Sam as payments owner", status="open", created=TODAY)
    L(("Task", "task-handoff"), "ASSIGNS", ("Person", "sam"))
    L(("Task", "task-handoff"), "ABOUT", ("System", "sys-pay"))
    L(("Task", "task-handoff"), "SOURCES", ("Ticket", "t-44"))
    L(("Task", "task-handoff"), "SOURCES", ("Message", "msg-handoff"))
    L(("Agent", "agent-clerk"), "WROTE", ("Task", "task-handoff"))

    return {"nodes": nodes, "links": links}
