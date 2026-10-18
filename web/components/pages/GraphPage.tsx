"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { ApplyResult, Risk, Stats, Task } from "@/lib/types";
import { useDesk } from "../DeskProvider";
import { Badge, Button, Card, Dot, ErrorLine, KIND_COLOR, PageHeader } from "../ui";

export default function GraphPage() {
  const { company, graph, graphLoading, refreshGraph, setDim, setLit, clearLit, selectNode, openContext } = useDesk();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [risks, setRisks] = useState<Risk[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [applied, setApplied] = useState<ApplyResult | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setDim(false);
    clearLit();
  }, [setDim, clearLit]);

  const load = useCallback(async () => {
    if (!company) return;
    const [t, r, s] = await Promise.all([api.tasks(company.id), api.risks(company.id), api.stats(company.id)]);
    setTasks(t);
    setRisks(r);
    setStats(s);
  }, [company]);

  useEffect(() => {
    setApplied(null);
  }, [company?.id]);

  useEffect(() => {
    load().catch((e) => setError(e.message));
  }, [load, graph]);

  const apply = async (task: Task) => {
    if (!company) return;
    setBusy(task.id);
    setError(null);
    try {
      const res = await api.apply(company.id, task.id);
      setApplied(res);
      await refreshGraph();
      await load();
      // old OWNS fades (dashed, ended), new OWNS lights
      const sys = res.system.id;
      setDim(true);
      setLit(
        [res.new_owner.id, sys, ...res.ended.map((e) => e.id)],
        [`${res.new_owner.id}|OWNS|${sys}`, ...res.ended.map((e) => `${e.id}|OWNS|${sys}`)],
      );
      setTimeout(() => {
        setDim(false);
        clearLit();
      }, 7000);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const reset = async () => {
    if (!company) return;
    if (!confirm("Rebuild the Lumen demo from the seed? Handoffs and stored sessions are discarded.")) return;
    setBusy("reset");
    try {
      await api.reset(company.id);
      setApplied(null);
      await refreshGraph();
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const open = tasks.filter((t) => t.status === "open");
  const done = tasks.filter((t) => t.status === "done");

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Graph"
        subtitle="The company map, proposed handoffs, and where knowledge sits on one person."
        right={
          <div className="flex items-center gap-2">
            <Button onClick={() => refreshGraph()} disabled={graphLoading}>
              {graphLoading ? "Loading…" : "Refresh"}
            </Button>
            <Button onClick={openContext}>Add context</Button>
          </div>
        }
      />
      <div className="flex-1 space-y-4 overflow-y-auto p-5">
        <ErrorLine message={error} />

        <Card title={`Proposed handoffs (${open.length})`}>
          {open.length === 0 && (
            <p className="text-sm text-muted">
              Nothing waiting. A ticket, a Slack message or an uploaded note that names a new owner becomes a task here. It does
              not change ownership until you click Apply.
            </p>
          )}
          <ul className="space-y-3">
            {open.map((t) => (
              <li key={t.id} className="rounded-lg border border-line bg-background p-3">
                <p className="text-sm font-medium">{t.title}</p>
                <p className="mt-1 text-sm text-muted">
                  {t.system.name}: <span className="text-foreground">{t.current_owner ?? "no owner"}</span>
                  {" → "}
                  <span className="text-accent">{t.assignee.name}</span>
                </p>
                {t.sources.length > 0 && (
                  <p className="mt-1 flex flex-wrap items-center gap-x-2 text-xs text-muted">
                    sourced by
                    {t.sources.map((s) => (
                      <button key={s.id} onClick={() => selectNode(s.id)} className="inline-flex items-center gap-1 hover:text-accent">
                        <Dot kind={s.kind} />
                        {s.name}
                      </button>
                    ))}
                  </p>
                )}
                <Button variant="primary" className="mt-3" disabled={busy === t.id} onClick={() => apply(t)}>
                  {busy === t.id ? "Applying…" : "Apply"}
                </Button>
              </li>
            ))}
          </ul>

          {applied && (
            <div className="fade-up mt-3 rounded-lg border border-emerald-800/60 bg-emerald-950/30 p-3 text-sm text-emerald-200">
              <p>
                {applied.new_owner.name} now owns {applied.system.name} (from {applied.new_owner.start}).
              </p>
              {applied.ended.map((e) => (
                <p key={e.id} className="mt-1 text-emerald-200/80">
                  {e.name}&apos;s OWNS link now ends {e.end}. It stays on the map, dashed.
                </p>
              ))}
              <p className="mt-1 text-emerald-200/80">Ask the owner question again: the next answer returns the new owner.</p>
            </div>
          )}

          {done.length > 0 && (
            <div className="mt-4">
              <h3 className="mb-1 text-xs font-medium uppercase tracking-wide text-muted">Applied</h3>
              <ul className="space-y-1 text-sm text-muted">
                {done.map((t) => (
                  <li key={t.id} className="flex items-center gap-2">
                    <Badge tone="ok">done</Badge>
                    {t.title}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Card>

        <Card title="Single-expert risk">
          {risks.length === 0 ? (
            <p className="text-sm text-muted">No system has exactly one person who authored its changes.</p>
          ) : (
            <ul className="space-y-1.5 text-sm">
              {risks.map((r) => (
                <li key={r.system}>
                  <span className="font-medium">{r.system}</span>
                  <span className="text-muted"> — only {r.authors.join(", ")} has authored a change</span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Map">
          <p className="text-sm text-muted">
            {graph.nodes.length} nodes drawn · {stats?.total_links ?? graph.links.length} links in the graph. Click a node to open its
            source, see its links, or remove a wrong one. Dashed links are ownership that has ended.
          </p>
          <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5">
            {Object.keys(KIND_COLOR).map((k) => (
              <span key={k} className="flex items-center gap-1.5 text-xs text-muted">
                <Dot kind={k} />
                {k}
              </span>
            ))}
          </div>
          {company?.id === "lumen" && (
            <Button className="mt-4" variant="danger" disabled={busy === "reset"} onClick={reset}>
              Reset demo to the seed
            </Button>
          )}
        </Card>
      </div>
    </div>
  );
}
