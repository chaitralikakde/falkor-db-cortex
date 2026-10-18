"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Connector, Department, Settings, Skill } from "@/lib/types";
import { useDesk } from "../DeskProvider";
import ModelTab from "./ModelTab";
import { Badge, Button, Card, ErrorLine, Field, Input, PageHeader, Tabs, Textarea, Toggle } from "../ui";

type Tab = "instructions" | "model" | "access" | "apps";

const TABS: { id: Tab; label: string }[] = [
  { id: "instructions", label: "Instructions" },
  { id: "model", label: "Model" },
  { id: "access", label: "Access" },
  { id: "apps", label: "Apps" },
];

function useSettings() {
  const { company } = useDesk();
  const [settings, setSettings] = useState<Settings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!company) return;
    api.settings(company.id).then(setSettings).catch((e) => setError(e.message));
  }, [company]);

  const save = async (patch: Partial<Settings>) => {
    if (!company) return;
    setError(null);
    try {
      setSettings(await api.saveSettings(company.id, patch));
      setSaved(true);
      setTimeout(() => setSaved(false), 1800);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return { settings, save, error, saved };
}

function SaveRow({ onSave, saved }: { onSave: () => void; saved: boolean }) {
  return (
    <div className="flex items-center gap-3">
      <Button variant="primary" onClick={onSave}>
        Save
      </Button>
      {saved && <span className="text-sm text-emerald-300">Saved</span>}
    </div>
  );
}

export default function SettingsPage() {
  const [tab, setTab] = useState<Tab>("instructions");
  return (
    <div className="flex h-full flex-col">
      <PageHeader title="Settings" subtitle="How this company's desk answers, and what it may touch." />
      <Tabs tabs={TABS} value={tab} onChange={setTab} />
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl space-y-4 p-5">
          {tab === "instructions" && <Instructions />}
          {tab === "model" && <ModelTab />}
          {tab === "access" && <AccessSection />}
          {tab === "apps" && <AppsSection />}
        </div>
      </div>
    </div>
  );
}

function Instructions() {
  const { settings, save, error, saved } = useSettings();
  const [prompt, setPrompt] = useState("");
  const [skills, setSkills] = useState<Skill[]>([]);
  const [open, setOpen] = useState<number | null>(null);
  const [draft, setDraft] = useState<Skill | null>(null);

  useEffect(() => {
    if (settings) {
      setPrompt(settings.super_prompt);
      setSkills(settings.skills);
    }
  }, [settings]);

  const update = (i: number, patch: Partial<Skill>) => setSkills(skills.map((s, j) => (j === i ? { ...s, ...patch } : s)));

  return (
    <>
      <ErrorLine message={error} />
      <Card title="Super prompt">
        <p className="mb-3 text-sm text-muted">One standing instruction for every answer. A skill never overrides it.</p>
        <Textarea rows={6} value={prompt} onChange={(e) => setPrompt(e.target.value)} className="font-mono" />
        <p className="mt-2 text-xs text-muted">
          Answers are phrased by rule from the rows the graph returned, so they cannot name anyone who is not in the Finding. The
          prompt is stored now and applied once a model is connected.
        </p>
      </Card>

      <Card
        title="Skills"
        right={
          <Button onClick={() => setDraft({ name: "", when: "", steps: "", on: true })} disabled={!!draft}>
            Add skill
          </Button>
        }
      >
        <ul className="divide-y divide-line">
          {skills.map((s, i) => (
            <li key={s.name + i} className="py-3 first:pt-0 last:pb-0">
              <div className="flex items-center gap-3">
                <Toggle on={s.on} onChange={(v) => update(i, { on: v })} label={s.name} />
                <button onClick={() => setOpen(open === i ? null : i)} className="min-w-0 flex-1 text-left">
                  <span className="block truncate text-sm font-medium">{s.name}</span>
                  <span className="block truncate text-xs text-muted">{s.when}</span>
                </button>
                <button onClick={() => setOpen(open === i ? null : i)} className="text-xs text-muted hover:text-foreground">
                  {open === i ? "Close" : "Edit"}
                </button>
              </div>
              {open === i && (
                <div className="fade-up mt-3 space-y-3 pl-12">
                  <Field label="When">
                    <Input value={s.when} onChange={(e) => update(i, { when: e.target.value })} />
                  </Field>
                  <Field label="Steps">
                    <Textarea rows={2} value={s.steps} onChange={(e) => update(i, { steps: e.target.value })} />
                  </Field>
                </div>
              )}
            </li>
          ))}
        </ul>

        {draft && (
          <div className="fade-up mt-4 space-y-3 rounded-lg border border-line bg-background p-3">
            <Field label="Name">
              <Input autoFocus value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
            </Field>
            <Field label="When">
              <Input value={draft.when} onChange={(e) => setDraft({ ...draft, when: e.target.value })} />
            </Field>
            <Field label="Steps">
              <Textarea rows={2} value={draft.steps} onChange={(e) => setDraft({ ...draft, steps: e.target.value })} />
            </Field>
            <div className="flex gap-2">
              <Button
                variant="primary"
                disabled={!draft.name.trim()}
                onClick={() => {
                  setSkills([...skills, draft]);
                  setDraft(null);
                }}
              >
                Add
              </Button>
              <Button onClick={() => setDraft(null)}>Cancel</Button>
            </div>
          </div>
        )}
        <p className="mt-3 text-xs text-muted">
          Turning off “Who owns this” or “Why we decided this” makes Ask refuse that kind of question.
        </p>
      </Card>

      <SaveRow saved={saved} onSave={() => save({ super_prompt: prompt, skills })} />
    </>
  );
}

function AccessSection() {
  const { company } = useDesk();
  const [cards, setCards] = useState<Connector[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const load = useCallback(async () => {
    if (!company) return;
    setCards(await api.connectors(company.id));
    setDepartments(await api.departments(company.id));
  }, [company]);
  useEffect(() => {
    load().catch(() => {});
  }, [load]);

  return (
    <>
      <Card title="Departments">
        <p className="mb-3 text-sm text-muted">
          Each Slack bot is assigned one of these. It can only name the systems listed. The web Ask page has no department, so it still
          sees everything.
        </p>
        <div className="space-y-3">
          {departments.map((d) => (
            <div key={d.id} className="rounded-lg border border-line px-3 py-2.5">
              <p className="text-sm font-medium">{d.name}</p>
              <p className="text-xs text-muted">{d.blurb}</p>
              <p className="mt-1.5 text-sm">
                {d.systems.map((s) => s.name).join(" · ") || "No systems labelled yet."}
              </p>
              <p className="text-xs text-muted">{d.people.map((p) => p.name).join(", ")}</p>
            </div>
          ))}
        </div>
      </Card>
      <Card title="Permissions">
        <table className="w-full text-sm">
          <thead className="text-left text-xs uppercase tracking-wide text-muted">
            <tr>
              <th className="pb-2 font-medium">Tool</th>
              <th className="pb-2 font-medium">Read</th>
              <th className="pb-2 font-medium">Write</th>
            </tr>
          </thead>
          <tbody>
            {cards.map((c) => (
              <tr key={c.id} className="border-t border-line">
                <td className="py-2.5">{c.name}</td>
                <td>
                  <Toggle
                    on={c.read}
                    disabled={!c.connected}
                    label={`${c.name} read`}
                    onChange={async (v) => {
                      if (company) await api.patchConnector(company.id, c.id, { read: v });
                      load();
                    }}
                  />
                </td>
                <td>
                  <Toggle
                    on={c.write}
                    disabled={!c.connected || !c.read}
                    label={`${c.name} write`}
                    onChange={async (v) => {
                      if (company) await api.patchConnector(company.id, c.id, { write: v });
                      load();
                    }}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-3 text-xs text-muted">
          Read is the default. Write switches are stored, but no connector write exists yet. The only write today is Apply on Graph.
        </p>
      </Card>

      <Card title="Admin" right={<Badge tone="warn">sign-in not built yet</Badge>}>
        <div className="flex items-center justify-between text-sm">
          <span>{company?.admin || "—"}</span>
          <Badge tone="ok">admin</Badge>
        </div>
        <p className="mt-3 text-xs text-muted">
          The person who created the company is its admin. Until sign-in exists, every visitor can use the admin controls.
        </p>
      </Card>

      <Card title="Keys and Forget" right={<Badge tone="warn">not built yet</Badge>}>
        <p className="text-sm text-muted">
          Set <code>MODEL_API_KEY</code> in the host&apos;s environment. The browser never holds it.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button disabled>Forget a file</Button>
          <Button disabled>Forget a channel</Button>
          <Button variant="danger" disabled>
            Forget the company graph
          </Button>
        </div>
      </Card>
    </>
  );
}

function AppsSection() {
  const apps = [
    { name: "Notion", text: "Write a decision page after the answer." },
    { name: "Google Drive", text: "Save the answer and its path as a file." },
    { name: "Calendar", text: "Book the handoff conversation." },
  ];
  return (
    <>
      <Card title="Apps" right={<Badge tone="warn">not built yet</Badge>}>
        <p className="mb-3 text-sm text-muted">
          A connector fills the graph. An app does something after the answer. Slack lives under Connectors.
        </p>
        <ul className="divide-y divide-line">
          {apps.map((a) => (
            <li key={a.name} className="flex items-center justify-between gap-3 py-2.5">
              <div>
                <p className="text-sm font-medium">{a.name}</p>
                <p className="text-xs text-muted">{a.text}</p>
              </div>
              <Button disabled>Connect</Button>
            </li>
          ))}
        </ul>
      </Card>
    </>
  );
}
