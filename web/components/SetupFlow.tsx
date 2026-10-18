"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Stats } from "@/lib/types";
import CompanySwitcher from "./CompanySwitcher";
import ContextPanel from "./ContextPanel";
import { useDesk } from "./DeskProvider";
import GraphCanvas from "./GraphCanvas";
import { CheckIcon } from "./icons";
import NodePanel from "./NodePanel";
import { Button, Dot, ErrorLine, Field, Input } from "./ui";

const STEPS = ["Company", "Add context", "Review"];

/**
 * First-run flow for a company: name it, give it documents, check the map, then Finish.
 * Chat stays closed until Finish so a half-loaded graph cannot answer with the wrong owner.
 */
export default function SetupFlow() {
  const { company, companies, newCompany, setNewCompany, reloadCompanies, setCompanyId, setPage, setDim, clearLit } = useDesk();
  const [step, setStep] = useState(newCompany ? 0 : 1);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);

  // starting a new company begins at step 1; picking one that is mid-setup resumes
  useEffect(() => {
    setStep(newCompany ? 0 : 1);
  }, [newCompany, company?.id]);

  useEffect(() => {
    setDim(false);
    clearLit();
  }, [setDim, clearLit, step]);

  const loadStats = useCallback(async () => {
    if (!company || newCompany) return;
    setStats(await api.stats(company.id));
  }, [company, newCompany]);

  useEffect(() => {
    setStats(null);
    loadStats().catch((e) => setError(e.message));
  }, [loadStats]);

  const create = async () => {
    if (!name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const c = await api.createCompany(name.trim());
      await reloadCompanies();
      setCompanyId(c.id);
      setNewCompany(false);
      setName("");
      setStep(1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const finish = async () => {
    if (!company) return;
    setBusy(true);
    setError(null);
    try {
      await api.finish(company.id);
      await reloadCompanies();
      setPage("ask");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const people = stats?.people ?? 0;
  const canCancel = newCompany && companies.some((c) => c.finished);

  return (
    <div className="flex h-full flex-col">
      <header className="flex h-14 shrink-0 items-center justify-between gap-4 border-b border-line bg-panel px-5">
        <div className="flex items-center gap-2">
          <span className="grid h-7 w-7 place-items-center rounded-lg bg-accent text-sm font-bold text-black">C</span>
          <span className="text-sm font-semibold">Cortex</span>
        </div>
        <Stepper step={step} />
        <div className="w-56">
          <CompanySwitcher />
        </div>
      </header>

      {step === 0 ? (
        <div className="grid flex-1 place-items-center p-6">
          <div className="fade-up w-full max-w-md">
            <h1 className="text-2xl font-semibold tracking-tight">Set up a company graph</h1>
            <p className="mt-2 text-sm text-muted">
              Each company gets its own graph in FalkorDB. Add its documents next and the map draws itself.
            </p>
            <div className="mt-6 space-y-4">
              <ErrorLine message={error} />
              <Field label="Company name">
                <Input
                  autoFocus
                  value={name}
                  placeholder="Acme"
                  onChange={(e) => setName(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && create()}
                />
              </Field>
              <div className="flex items-center gap-2">
                <Button variant="primary" disabled={busy || !name.trim()} onClick={create}>
                  {busy ? "Creating…" : "Continue"}
                </Button>
                {canCancel && <Button onClick={() => setNewCompany(false)}>Cancel</Button>}
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="flex min-h-0 flex-1">
          <section className="flex w-[clamp(400px,36vw,520px)] shrink-0 flex-col border-r border-line">
            <div className="flex-1 overflow-y-auto p-6">
              {step === 1 && (
                <div className="fade-up space-y-5">
                  <div>
                    <h1 className="text-xl font-semibold tracking-tight">Add what {company?.name ?? "the company"} knows</h1>
                    <p className="mt-1 text-sm text-muted">
                      Team lists, ownership notes, ADRs, handoffs. People, systems and decisions they name become nodes on the map.
                    </p>
                  </div>
                  <ErrorLine message={error} />
                  <ContextPanel onChanged={() => loadStats().catch(() => {})} />
                </div>
              )}

              {step === 2 && (
                <div className="fade-up space-y-5">
                  <div>
                    <h1 className="text-xl font-semibold tracking-tight">Check the map</h1>
                    <p className="mt-1 text-sm text-muted">
                      Click a node to see its links and remove a wrong one. Questions open once you finish.
                    </p>
                  </div>
                  <ErrorLine message={error} />
                  <div className="rounded-xl border border-line bg-panel p-4">
                    <p className="text-2xl font-semibold">
                      {stats?.total_nodes ?? 0}
                      <span className="ml-1 text-sm font-normal text-muted">nodes</span>
                      <span className="ml-4">{stats?.total_links ?? 0}</span>
                      <span className="ml-1 text-sm font-normal text-muted">links</span>
                    </p>
                    {stats && (
                      <div className="mt-3 flex flex-wrap gap-2">
                        {Object.entries(stats.nodes)
                          .sort((a, b) => b[1] - a[1])
                          .map(([k, v]) => (
                            <span key={k} className="flex items-center gap-1.5 rounded-full border border-line px-2.5 py-1 text-xs">
                              <Dot kind={k} />
                              {k} <span className="text-muted">{v}</span>
                            </span>
                          ))}
                      </div>
                    )}
                  </div>
                  {people < 1 && <p className="text-sm text-amber-300">No people yet. Go back and add at least one.</p>}
                </div>
              )}
            </div>

            <footer className="flex shrink-0 items-center justify-between gap-3 border-t border-line bg-panel px-6 py-3">
              {step === 1 ? (
                <>
                  <span className="text-xs text-muted">
                    {people > 0 ? `${people} ${people === 1 ? "person" : "people"} mapped` : "Add at least one person to continue"}
                  </span>
                  <Button variant="primary" disabled={people < 1} onClick={() => setStep(2)}>
                    Review the map
                  </Button>
                </>
              ) : (
                <>
                  <Button onClick={() => setStep(1)}>Back</Button>
                  <Button variant="primary" disabled={busy || people < 1} onClick={finish}>
                    {busy ? "Finishing…" : "Finish and open chat"}
                  </Button>
                </>
              )}
            </footer>
          </section>

          <section className="relative min-w-0 flex-1 bg-background">
            <GraphCanvas />
            <NodePanel canFix={step === 2} />
          </section>
        </div>
      )}
    </div>
  );
}

function Stepper({ step }: { step: number }) {
  return (
    <ol className="flex items-center gap-2 text-sm">
      {STEPS.map((label, i) => {
        const done = i < step;
        const active = i === step;
        return (
          <li key={label} className="flex items-center gap-2">
            {i > 0 && <span className={`h-px w-8 ${done || active ? "bg-accent/60" : "bg-line"}`} />}
            <span
              className={`grid h-5 w-5 place-items-center rounded-full text-[11px] font-semibold ${
                done ? "bg-accent text-black" : active ? "border border-accent text-accent" : "border border-line text-muted"
              }`}
            >
              {done ? <CheckIcon size={12} /> : i + 1}
            </span>
            <span className={active ? "text-foreground" : "text-muted"}>{label}</span>
          </li>
        );
      })}
    </ol>
  );
}
