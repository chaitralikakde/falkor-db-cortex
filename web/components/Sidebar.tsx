"use client";

import type { ReactNode } from "react";
import CompanySwitcher from "./CompanySwitcher";
import { useDesk, type PageId } from "./DeskProvider";
import { AnswersIcon, AskIcon, GraphIcon, SettingsIcon, SourcesIcon } from "./icons";

const ITEMS: { id: PageId; label: string; icon: ReactNode }[] = [
  { id: "ask", label: "Ask", icon: <AskIcon /> },
  { id: "graph", label: "Graph", icon: <GraphIcon /> },
  { id: "sources", label: "Connectors", icon: <SourcesIcon /> },
  { id: "answers", label: "Answers", icon: <AnswersIcon /> },
  { id: "settings", label: "Settings", icon: <SettingsIcon /> },
];

export default function Sidebar() {
  const { page, setPage } = useDesk();

  return (
    <aside className="flex h-full w-56 shrink-0 flex-col border-r border-line bg-panel">
      <div className="flex items-center gap-2 px-4 pb-3 pt-4">
        <span className="grid h-7 w-7 place-items-center rounded-lg bg-accent text-sm font-bold text-black">C</span>
        <span className="text-sm font-semibold">Cortex</span>
      </div>

      <div className="px-3 pb-3">
        <CompanySwitcher />
      </div>

      <nav className="flex-1 space-y-0.5 px-2">
        {ITEMS.map((it) => {
          const active = page === it.id;
          return (
            <button
              key={it.id}
              onClick={() => setPage(it.id)}
              className={`flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm transition ${
                active ? "bg-panel-2 text-foreground" : "text-muted hover:bg-panel-2/60 hover:text-foreground"
              }`}
            >
              <span className={active ? "text-accent" : ""}>{it.icon}</span>
              {it.label}
            </button>
          );
        })}
      </nav>

      <p className="px-4 py-3 text-[11px] leading-snug text-muted">No path in the graph, no answer.</p>
    </aside>
  );
}
