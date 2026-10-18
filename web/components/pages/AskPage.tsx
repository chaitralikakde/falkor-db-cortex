"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { AskResult, Step } from "@/lib/types";
import { useDesk } from "../DeskProvider";
import { Badge, Button, Dot, ErrorLine, PageHeader } from "../ui";

const LUMEN_QUESTIONS = [
  "What did we already say about Payments API?",
  "Who owns it, and who else can fix it?",
  "Why did we move the database?",
  "Who owns Payments API?",
];

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

type StepState = { step: Step; phase: "running" | "done" };

export default function AskPage() {
  const { company, graph, refreshGraph, lit, lightNode, lightLink, clearLit, setDim, selectNode, openContext } = useDesk();
  const [question, setQuestion] = useState("");
  const [running, setRunning] = useState(false);
  const [model, setModel] = useState("");
  const [shown, setShown] = useState<StepState[]>([]);
  const [result, setResult] = useState<AskResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const run = useRef(0);

  useEffect(() => {
    setDim(true);
  }, [setDim]);

  useEffect(() => {
    if (!company) return;
    api.settings(company.id).then((s) => setModel(s.model.label)).catch(() => {});
    setResult(null);
    setShown([]);
    setError(null);
  }, [company]);

  const suggestions = useMemo(() => {
    if (company?.id === "lumen") return LUMEN_QUESTIONS;
    const sys = graph.nodes.find((n) => n.label === "System");
    return sys ? [`Who owns ${sys.data.name}?`, `Why did we decide ${sys.data.name}?`] : [];
  }, [company, graph.nodes]);

  const ask = async (q: string) => {
    if (!company || !q.trim() || running) return;
    const myRun = ++run.current;
    const alive = () => run.current === myRun;
    setRunning(true);
    setError(null);
    setResult(null);
    setShown([]);
    clearLit();
    setDim(true);
    try {
      const res = await api.ask(company.id, q.trim());
      await refreshGraph(); // the Session, Finding and Task nodes just written are on the map now
      for (const step of res.steps) {
        if (!alive()) return;
        setShown((s) => [...s, { step, phase: "running" }]);
        await sleep(450);
        if (!alive()) return;
        setShown((s) => s.map((x) => (x.step === step ? { ...x, phase: "done" } : x)));
        const linkSet = step.links;
        for (const n of step.nodes) {
          if (!alive()) return;
          lightNode(n.id);
          for (const l of linkSet) {
            if (lit.current.nodes.has(l.source) && lit.current.nodes.has(l.target)) lightLink(l.id);
          }
          await sleep(400);
        }
        for (const l of linkSet) {
          if (lit.current.nodes.has(l.source) && lit.current.nodes.has(l.target)) lightLink(l.id);
        }
      }
      if (alive()) setResult(res);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      if (alive()) setRunning(false);
    }
  };

  const open = (id: string) => selectNode(id);

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Ask"
        subtitle={company ? `${company.name} · answers come only from paths in the graph` : ""}
        right={
          <Button onClick={openContext} className="shrink-0 whitespace-nowrap">
            Add context
          </Button>
        }
      />
      <div className="flex-1 space-y-4 overflow-y-auto p-5">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            ask(question);
          }}
          className="flex gap-2"
        >
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Who owns Payments API, and who else can fix it?"
            className="flex-1 rounded-xl border border-line bg-panel px-4 py-3 text-sm outline-none placeholder:text-muted/70 focus:border-accent/70"
          />
          <Button variant="primary" type="submit" disabled={running || !question.trim()} className="px-5">
            {running ? "Running…" : "Ask"}
          </Button>
        </form>

        {suggestions.length > 0 && !running && (
          <div className="flex flex-wrap gap-2">
            {suggestions.map((s) => (
              <button
                key={s}
                onClick={() => {
                  setQuestion(s);
                  ask(s);
                }}
                className="rounded-full border border-line bg-panel px-3 py-1 text-xs text-muted hover:border-accent/60 hover:text-foreground"
              >
                {s}
              </button>
            ))}
          </div>
        )}

        <ErrorLine message={error} />

        {shown.length > 0 && (
          <ol className="space-y-2">
            {shown.map(({ step, phase }, i) => (
              <li key={i} className="fade-up rounded-xl border border-line bg-panel p-3">
                <div className="flex items-center gap-2 text-sm">
                  <Badge tone={step.agent === "Mapper" ? "muted" : "warn"}>{step.agent}</Badge>
                  <span className="font-mono text-[13px]">
                    {phase === "running" ? `Running ${step.tool} on FalkorDB…` : step.tool}
                  </span>
                </div>
                <code className="mt-2 block max-h-20 overflow-hidden whitespace-pre-wrap break-words rounded-lg bg-background px-2.5 py-1.5 font-mono text-[11px] leading-snug text-muted">
                  {step.cypher}
                </code>
                {phase === "done" && (
                  <p className="mt-1.5 text-xs text-muted">
                    {step.nodes.length} nodes · {step.links.length} links · {step.ms} ms
                  </p>
                )}
              </li>
            ))}
          </ol>
        )}

        {result && (
          <div
            className={`fade-up rounded-xl border p-4 ${
              result.refused ? "border-line bg-panel" : "border-accent/40 bg-accent/5"
            }`}
          >
            {result.sentence.split("\n").map((line, i) => (
              <p key={i} className={`text-sm leading-relaxed ${i > 0 ? "mt-2" : "text-base font-medium"}`}>
                {line}
              </p>
            ))}
            {result.sources.length > 0 && (
              <div className="mt-4">
                <h3 className="text-xs font-medium uppercase tracking-wide text-muted">Sources</h3>
                <ul className="mt-2 space-y-1">
                  {result.sources.map((s) => (
                    <li key={s.id} className="flex items-center gap-2 text-sm">
                      <Dot kind={s.kind} />
                      <button className="text-left hover:text-accent" onClick={() => open(s.id)} title="Show on the map">
                        {s.name}
                      </button>
                      <span className="text-xs text-muted">{s.kind}{s.date ? ` · ${s.date}` : ""}</span>
                      {s.url && (
                        <a href={s.url} target="_blank" rel="noreferrer" className="ml-auto text-xs text-accent hover:underline">
                          open ↗
                        </a>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <p className="mt-3 text-xs text-muted">
              {result.ms} ms total{result.session ? ` · stored as ${result.session}` : ""}
              {result.refused ? " · no path returned, so nothing is guessed" : ""}
            </p>
          </div>
        )}
      </div>
      {model && <p className="border-t border-line px-5 py-2 text-[11px] text-muted">Model: {model}</p>}
    </div>
  );
}
