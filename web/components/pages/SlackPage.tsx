"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Department, SlackStatus } from "@/lib/types";
import { useDesk } from "../DeskProvider";
import SlackBotCard from "./SlackBotCard";
import { Button, ErrorLine, Field, Input, PageHeader } from "../ui";

export default function SlackPage({ onBack }: { onBack: () => void }) {
  const { company } = useDesk();
  const [status, setStatus] = useState<SlackStatus | null>(null);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!company) return;
    const [s, d] = await Promise.all([api.slack(company.id), api.departments(company.id)]);
    setStatus(s);
    setDepartments(d);
  }, [company]);

  useEffect(() => {
    setStatus(null);
    setError(null);
    setOpenId(null);
    load().catch((e) => setError(e.message));
  }, [load]);

  useEffect(() => {
    const t = setInterval(() => load().catch(() => {}), 5000);
    return () => clearInterval(t);
  }, [load]);

  const bots = status?.bots ?? [];
  const showForm = adding || (status !== null && bots.length === 0);

  return (
    <div className="h-full overflow-y-auto">
      <PageHeader
        title="Slack"
        right={
          <div className="flex gap-2">
            <Button onClick={onBack}>← Connectors</Button>
            {bots.length > 0 && !adding && (
              <Button variant="primary" onClick={() => setAdding(true)}>
                Add bot
              </Button>
            )}
          </div>
        }
      />
      <div className="mx-auto max-w-3xl space-y-4 p-5">
        <ErrorLine message={error} />
        {status === null && !error && <p className="text-sm text-muted">Loading…</p>}

        {status && (
          <div className="overflow-hidden rounded-xl border border-line">
            {bots.map((b) => (
              <div key={b.id} className="border-b border-line last:border-b-0">
                <SlackBotCard
                  bot={b}
                  departments={departments}
                  open={openId === b.id}
                  onOpen={() => setOpenId(openId === b.id ? null : b.id)}
                  onChange={setStatus}
                />
              </div>
            ))}
            {showForm && (
              <AddBot
                first={bots.length === 0}
                departments={departments}
                onDone={(s) => {
                  setStatus(s);
                  setAdding(false);
                  const added = s.bots[s.bots.length - 1];
                  if (added) setOpenId(added.id);
                }}
                onCancel={bots.length ? () => setAdding(false) : undefined}
              />
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function AddBot({
  first,
  departments,
  onDone,
  onCancel,
}: {
  first: boolean;
  departments: Department[];
  onDone: (s: SlackStatus) => void;
  onCancel?: () => void;
}) {
  const { company } = useDesk();
  const [token, setToken] = useState("");
  const [label, setLabel] = useState("");
  const [department, setDepartment] = useState("");
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const connect = async () => {
    if (!company || !token.trim()) return;
    setBusy(true);
    setError(null);
    try {
      onDone(await api.addSlackBot(company.id, token.trim(), label.trim(), department));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3 p-4">
      <p className="text-sm font-medium">{first ? "Connect a bot" : "Add a bot"}</p>
      <ErrorLine message={error} />
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Name">
          <Input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Engineering brain" />
        </Field>
        <Field label="Department">
          <select
            value={department}
            onChange={(e) => setDepartment(e.target.value)}
            className="w-full rounded-lg border border-line bg-background px-3 py-2 text-sm outline-none focus:border-accent/70"
          >
            <option value="">Whole company</option>
            {departments.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
        </Field>
        <div className="sm:col-span-2">
          <Field label="Bot token">
            <Input
              type="password"
              autoComplete="off"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && connect()}
              placeholder="xoxb-…"
            />
          </Field>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="primary" onClick={connect} disabled={busy || !token.trim()}>
          {busy ? "Checking…" : "Connect"}
        </Button>
        {onCancel && <Button onClick={onCancel}>Cancel</Button>}
        <a href="https://api.slack.com/apps?new_app=1" target="_blank" rel="noreferrer" className="ml-auto text-xs text-muted hover:text-foreground">
          Create app
        </a>
        <button
          type="button"
          className="text-xs text-muted hover:text-foreground"
          onClick={async () => {
            const m = await api.slackManifest();
            await navigator.clipboard.writeText(JSON.stringify(m, null, 2));
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
          }}
        >
          {copied ? "Copied" : "Copy manifest"}
        </button>
      </div>
    </div>
  );
}
