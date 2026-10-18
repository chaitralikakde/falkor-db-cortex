"use client";

import ContextPanel from "./ContextPanel";
import { useDesk } from "./DeskProvider";
import { CloseIcon } from "./icons";

/** Slides over the left panel so the map stays visible while new nodes light up. */
export default function ContextDrawer() {
  const { company, setContextOpen } = useDesk();

  return (
    <div className="fade-up absolute inset-y-0 left-0 z-20 flex w-[clamp(380px,34vw,480px)] flex-col border-r border-line bg-panel shadow-2xl">
      <div className="flex items-start justify-between gap-3 border-b border-line px-5 py-4">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">Add context</h2>
          <p className="mt-0.5 text-sm text-muted">New documents for {company?.name}. Nodes light up on the map.</p>
        </div>
        <button
          onClick={() => setContextOpen(false)}
          aria-label="Close"
          className="rounded-lg p-1.5 text-muted hover:bg-panel-2 hover:text-foreground"
        >
          <CloseIcon />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-5">
        <ContextPanel />
      </div>
      <p className="border-t border-line px-5 py-3 text-xs text-muted">
        Uploads never change an owner. A note that names a new owner shows up on Graph as a proposed handoff.
      </p>
    </div>
  );
}
