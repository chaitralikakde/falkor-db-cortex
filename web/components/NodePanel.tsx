"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { NodeDetail } from "@/lib/types";
import { useDesk } from "./DeskProvider";
import { Button, Dot } from "./ui";

const HIDDEN = new Set(["id", "name", "body", "source", "url"]);

/** Click a node on the map: its properties, its links, a way to open the source, and a way to remove a wrong link. */
export default function NodePanel({ canFix }: { canFix: boolean }) {
  const { company, selectedId, selectNode, refreshGraph, setError } = useDesk();
  const [detail, setDetail] = useState<NodeDetail | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    if (!company || !selectedId) {
      setDetail(null);
      return;
    }
    let live = true;
    api
      .node(company.id, selectedId)
      .then((d) => live && setDetail(d))
      .catch(() => live && setDetail(null));
    return () => {
      live = false;
    };
  }, [company, selectedId]);

  if (!selectedId || !detail || !company) return null;
  const { node, links } = detail;
  const url = node.data.url;

  const remove = async (l: NodeDetail["links"][number]) => {
    setBusy(`${l.source}|${l.rel}|${l.target}`);
    try {
      await api.unlink(company.id, l.source, l.rel, l.target);
      await refreshGraph();
      setDetail(await api.node(company.id, node.id));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="fade-up absolute right-3 top-3 z-10 max-h-[calc(100%-1.5rem)] w-80 overflow-y-auto rounded-xl border border-line bg-panel/95 p-4 shadow-2xl backdrop-blur">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-xs text-muted">
            <Dot kind={node.label} />
            {node.label}
          </div>
          <h3 className="mt-0.5 break-words text-base font-semibold">{node.data.name}</h3>
        </div>
        <button onClick={() => selectNode(null)} className="text-muted hover:text-foreground" aria-label="Close">
          ×
        </button>
      </div>

      {url && (
        <a
          href={url}
          target="_blank"
          rel="noreferrer"
          className="mt-2 inline-block text-sm text-accent underline-offset-2 hover:underline"
        >
          Open source ↗
        </a>
      )}

      <dl className="mt-3 space-y-1 text-sm">
        {Object.entries(node.data)
          .filter(([k, v]) => !HIDDEN.has(k) && v !== "" && v !== null)
          .map(([k, v]) => (
            <div key={k} className="flex gap-2">
              <dt className="w-20 shrink-0 text-muted">{k}</dt>
              <dd className="min-w-0 break-words">{String(v)}</dd>
            </div>
          ))}
        {typeof node.data.body === "string" && node.data.body && (
          <p className="mt-2 rounded-lg bg-background p-2 text-xs leading-relaxed text-muted">
            {node.data.body.slice(0, 400)}
            {node.data.body.length > 400 ? "…" : ""}
          </p>
        )}
      </dl>

      <h4 className="mb-1 mt-4 text-xs font-medium uppercase tracking-wide text-muted">
        Links ({links.length})
      </h4>
      <ul className="space-y-1">
        {links.map((l) => {
          const key = `${l.source}|${l.rel}|${l.target}`;
          return (
            <li key={key + l.direction} className="flex items-center gap-2 text-sm">
              <span className="text-muted">{l.direction === "out" ? "→" : "←"}</span>
              <span className="rounded bg-[#222c39] px-1.5 py-0.5 text-[11px]">{l.rel}</span>
              <button
                className="min-w-0 flex-1 truncate text-left hover:text-accent"
                onClick={() => selectNode(l.other.id)}
              >
                {l.other.name}
              </button>
              {typeof l.props.end === "string" && <span className="text-[11px] text-muted">ended {l.props.end}</span>}
              {canFix && (
                <button
                  disabled={busy === key}
                  onClick={() => remove(l)}
                  className="text-xs text-red-400 hover:text-red-300 disabled:opacity-40"
                  title="Remove this link"
                >
                  remove
                </button>
              )}
            </li>
          );
        })}
        {links.length === 0 && <li className="text-sm text-muted">No links.</li>}
      </ul>
      {canFix && (
        <p className="mt-3 text-[11px] text-muted">
          Removing a link deletes only that link. The nodes stay.
        </p>
      )}
      <Button className="mt-3 w-full" onClick={() => selectNode(null)}>
        Close
      </Button>
    </div>
  );
}
