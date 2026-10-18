"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Connector } from "@/lib/types";
import { useDesk } from "../DeskProvider";
import GitHubPage from "./GitHubPage";
import JiraPage from "./JiraPage";
import LinearPage from "./LinearPage";
import NotionPage from "./NotionPage";
import SlackPage from "./SlackPage";
import { Badge, Button, Card, ErrorLine, PageHeader } from "../ui";

type SourceView = "list" | "slack" | "github" | "jira" | "linear" | "notion";
const LIVE: SourceView[] = ["slack", "github", "jira", "linear", "notion"];

const FALLBACK: Record<string, string> = {
  upload: "Markdown, text and PDF files, plus people added by hand.",
  slack: "Tag a bot in Slack and it answers from the graph, with sources.",
  github: "Repositories and pull requests: who wrote and reviewed what.",
  jira: "Projects and issues become tickets on the graph.",
  linear: "Teams and issues become tickets on the graph.",
  notion: "Databases and pages become documents on the graph.",
};

export default function SourcesPage() {
  const { company, openContext } = useDesk();
  const [cards, setCards] = useState<Connector[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<SourceView>("list");

  const load = useCallback(async () => {
    if (!company) return;
    setCards(await api.connectors(company.id));
  }, [company]);

  useEffect(() => {
    if (view === "list") load().catch((e) => setError(e.message));
  }, [view, load]);

  if (view === "slack") return <SlackPage onBack={() => setView("list")} />;
  if (view === "github") return <GitHubPage onBack={() => setView("list")} />;
  if (view === "jira") return <JiraPage onBack={() => setView("list")} />;
  if (view === "linear") return <LinearPage onBack={() => setView("list")} />;
  if (view === "notion") return <NotionPage onBack={() => setView("list")} />;

  return (
    <div className="h-full overflow-y-auto">
      <PageHeader
        title="Connectors"
        subtitle="Where the graph gets its facts. Writes back to a tool stay off until an admin switches them on."
        right={<Button variant="primary" onClick={openContext}>Add context</Button>}
      />
      <div className="space-y-4 p-5">
        <ErrorLine message={error} />
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          {cards.map((c) => (
            <Card
              key={c.id}
              title={c.name}
              right={<Badge tone={c.connected ? "ok" : "muted"}>{c.connected ? "connected" : "not connected"}</Badge>}
            >
              <p className="text-sm text-muted">{c.detail ?? FALLBACK[c.id] ?? "Needs a token."}</p>
              {c.id !== "slack" && <p className="mt-2 text-xs text-muted">Last sync: {c.last_sync ?? "never"}</p>}

              {c.id === "upload" ? (
                <div className="mt-4">
                  <Button onClick={openContext}>Upload more documents</Button>
                </div>
              ) : LIVE.includes(c.id as SourceView) ? (
                <div className="mt-4">
                  <Button variant={c.connected ? "ghost" : "primary"} onClick={() => setView(c.id as SourceView)}>
                    {c.connected ? "Manage" : "Connect"} {c.name}
                  </Button>
                </div>
              ) : null}
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}
