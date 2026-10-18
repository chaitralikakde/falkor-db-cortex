"use client";

import { useEffect } from "react";
import ContextDrawer from "./ContextDrawer";
import { DeskProvider, MAP_PAGES, useDesk, type PageId } from "./DeskProvider";
import GraphCanvas from "./GraphCanvas";
import NodePanel from "./NodePanel";
import SetupFlow from "./SetupFlow";
import Sidebar from "./Sidebar";
import AskPage from "./pages/AskPage";
import GraphPage from "./pages/GraphPage";
import SettingsPage from "./pages/SettingsPage";
import SourcesPage from "./pages/SourcesPage";
import { AnswersPage } from "./pages/AnswersPage";

function Page({ id }: { id: PageId }) {
  switch (id) {
    case "ask":
      return <AskPage />;
    case "graph":
      return <GraphPage />;
    case "sources":
      return <SourcesPage />;
    case "answers":
      return <AnswersPage />;
    case "settings":
      return <SettingsPage />;
  }
}

function ErrorBanner() {
  const { error, setError } = useDesk();
  if (!error) return null;
  return (
    <div className="flex items-center justify-between gap-3 border-b border-red-900/60 bg-red-950/50 px-4 py-2 text-sm text-red-200">
      <span>
        {error}
        {error.toLowerCase().includes("fetch") || error.includes("500") ? " — is the API running on port 8000?" : ""}
      </span>
      <button onClick={() => setError(null)} className="text-red-300 hover:text-white">
        dismiss
      </button>
    </div>
  );
}

function Shell() {
  const { page, graph, graphLoading, company, companiesLoaded, newCompany, contextOpen, setContextOpen, openContext } = useDesk();
  const withMap = MAP_PAGES.has(page);

  useEffect(() => {
    if (!withMap) setContextOpen(false);
  }, [withMap, setContextOpen]);

  if (!companiesLoaded) {
    return (
      <div className="grid h-full place-items-center text-sm text-muted">
        <ErrorBanner />
        Loading…
      </div>
    );
  }

  // New company, or one that has not been finished yet: the guided flow replaces the app.
  if (newCompany || (company && !company.finished)) {
    return (
      <div className="flex h-full flex-col">
        <ErrorBanner />
        <div className="min-h-0 flex-1">
          <SetupFlow />
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full">
      <Sidebar />
      <main className="flex min-w-0 flex-1 flex-col">
        <ErrorBanner />
        <div className="relative flex min-h-0 flex-1">
          <section className={withMap ? "w-[clamp(380px,34vw,480px)] shrink-0 border-r border-line" : "min-w-0 flex-1"}>
            <Page id={page} />
          </section>
          {withMap && (
            <section className="relative min-w-0 flex-1 bg-background">
              <GraphCanvas />
              <NodePanel canFix={page === "graph"} />
              <div className="pointer-events-none absolute bottom-3 left-3 rounded-lg border border-line bg-panel/90 px-3 py-1.5 text-xs text-muted backdrop-blur">
                {graphLoading ? "Loading graph…" : `${company?.name ?? ""} · ${graph.nodes.length} nodes · ${graph.links.length} links`}
              </div>
              {!graphLoading && graph.nodes.length === 0 && (
                <div className="absolute inset-0 grid place-items-center">
                  <div className="max-w-xs text-center">
                    <p className="text-sm font-medium">This graph is empty.</p>
                    <p className="mt-1 text-sm text-muted">Add documents and the nodes will draw here.</p>
                    <button onClick={openContext} className="mt-3 rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-black">
                      Add context
                    </button>
                  </div>
                </div>
              )}
            </section>
          )}
          {withMap && contextOpen && <ContextDrawer />}
        </div>
      </main>
    </div>
  );
}

export default function AppShell() {
  return (
    <DeskProvider>
      <Shell />
    </DeskProvider>
  );
}
