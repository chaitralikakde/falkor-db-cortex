"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { LinearStatus, LinearTeam } from "@/lib/types";
import { useDesk } from "../DeskProvider";
import { Badge, Button, Card, ErrorLine, Field, Input, PageHeader, Segmented, Toggle } from "../ui";

export default function LinearPage({ onBack }: { onBack: () => void }) {
  const { company } = useDesk();
  const [status, setStatus] = useState<LinearStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!company) return;
    setStatus(await api.linear(company.id));
  }, [company]);

  useEffect(() => {
    setStatus(null);
    setError(null);
    load().catch((e) => setError(e.message));
  }, [load]);

  return (
    <div className="h-full overflow-y-auto">
      <PageHeader title="Linear" right={<Button onClick={onBack}>← Connectors</Button>} />
      <div className="mx-auto max-w-3xl space-y-4 p-5">
        <ErrorLine message={error} />
        {status === null && !error && <p className="text-sm text-muted">Loading…</p>}
        {status && !status.connected && <Connect status={status} onDone={setStatus} />}
        {status?.connected && <Connected status={status} onChange={setStatus} />}
      </div>
    </div>
  );
}

function Connect({ status, onDone }: { status: LinearStatus; onDone: (s: LinearStatus) => void }) {
  const { company } = useDesk();
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState<"env" | "token" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const connect = async (useEnv: boolean) => {
    if (!company) return;
    setBusy(useEnv ? "env" : "token");
    setError(null);
    try {
      onDone(await api.connectLinear(company.id, useEnv ? "" : token.trim(), useEnv));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <Card title="Connect">
      <div className="space-y-3">
        <ErrorLine message={error} />
        {status.env_available && (
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm">Server key {status.env_hint}</p>
            <Button variant="primary" onClick={() => connect(true)} disabled={busy !== null}>
              {busy === "env" ? "Checking…" : "Use it"}
            </Button>
          </div>
        )}
        <Field label="API key">
          <Input
            type="password"
            autoComplete="off"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && token.trim() && connect(false)}
            placeholder="lin_api_…"
          />
        </Field>
        <Button variant="primary" onClick={() => connect(false)} disabled={busy !== null || !token.trim()}>
          {busy === "token" ? "Checking…" : "Connect"}
        </Button>
      </div>
    </Card>
  );
}

function Connected({ status, onChange }: { status: LinearStatus; onChange: (s: LinearStatus) => void }) {
  const { company, refreshGraph } = useDesk();
  const [teams, setTeams] = useState<LinearTeam[] | null>(null);
  const [filter, setFilter] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadTeams = useCallback(async () => {
    if (!company) return;
    try {
      setTeams(await api.linearTeams(company.id));
    } catch (e) {
      setError((e as Error).message);
      setTeams((cur) => cur ?? []);
    }
  }, [company]);

  useEffect(() => {
    loadTeams();
  }, [loadTeams]);

  const picked = useMemo(() => new Set(status.teams), [status.teams]);
  const shown = useMemo(() => {
    const q = filter.trim().toLowerCase();
    return (teams ?? [])
      .filter((t) => t.key.toLowerCase().includes(q) || t.name.toLowerCase().includes(q))
      .sort((a, b) => Number(picked.has(b.id)) - Number(picked.has(a.id)));
  }, [teams, filter, picked]);

  const act = async (key: string, fn: () => Promise<LinearStatus>) => {
    setBusy(key);
    setError(null);
    try {
      onChange(await fn());
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    } finally {
      setBusy(null);
    }
  };

  const res = status.last_result;

  return (
    <>
      <ErrorLine message={error} />
      <Card title="Account" right={<Badge tone={status.token_missing ? "warn" : "ok"}>{status.token_missing ? "token missing" : "connected"}</Badge>}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm">
            <span className="font-medium">{status.name || status.email || "Linear"}</span>{" "}
            <span className="text-muted">{status.email}</span>
          </p>
          <Button
            variant="danger"
            disabled={busy !== null}
            onClick={() => {
              if (!company || !confirm("Disconnect Linear?")) return;
              act("disconnect", () => api.disconnectLinear(company.id));
            }}
          >
            Disconnect
          </Button>
        </div>
      </Card>

      <Card title="Teams" right={<span className="text-xs text-muted">{status.teams.length} selected</span>}>
        <div className="mb-2 flex items-center gap-2">
          <Input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter" aria-label="Filter teams" />
          <Button onClick={loadTeams} disabled={busy !== null} className="shrink-0">
            Refresh
          </Button>
        </div>
        {teams === null ? (
          <p className="text-sm text-muted">Loading…</p>
        ) : shown.length === 0 ? (
          <p className="rounded-lg border border-line px-3 py-3 text-sm text-muted">
            {teams.length === 0 ? "No teams" : "No match"}
          </p>
        ) : (
          <ul className="max-h-96 divide-y divide-line overflow-y-auto rounded-lg border border-line">
            {shown.map((t) => (
              <li key={t.id} className="flex items-center gap-3 px-3 py-2">
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">{t.key || t.name}</span>
                  <span className="block truncate text-xs text-muted">{t.name}</span>
                </span>
                <Toggle
                  on={picked.has(t.id)}
                  label={`Sync ${t.key || t.name}`}
                  disabled={busy === t.id || (!picked.has(t.id) && status.teams.length >= 25)}
                  onChange={(v) => {
                    if (!company) return;
                    const next = v ? [...status.teams, t.id] : status.teams.filter((id) => id !== t.id);
                    act(t.id, () => api.patchLinear(company.id, { teams: next }));
                  }}
                />
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title="Sync">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="text-sm">Issues per team</span>
            <Segmented
              options={status.issue_limits.map((n) => ({ id: String(n), label: String(n) }))}
              value={String(status.issue_limit)}
              onChange={(v) => company && act("limit", () => api.patchLinear(company.id, { issue_limit: Number(v) }))}
            />
          </div>
          <Button
            variant="primary"
            onClick={async () => {
              if (!company) return;
              if (await act("sync", () => api.syncLinear(company.id))) await refreshGraph().catch(() => {});
            }}
            disabled={busy !== null || status.teams.length === 0 || status.token_missing}
          >
            {busy === "sync" ? "Syncing…" : "Sync now"}
          </Button>
        </div>
        {res && (
          <div className="mt-3 rounded-lg border border-line bg-background p-3 text-sm">
            <p className="text-xs text-muted">{res.at}</p>
            <p className="mt-1">
              {res.teams} teams, {res.tickets} tickets
              {res.people_linked > 0 && `, ${res.people_linked} people matched`}
              {res.people_added.length > 0 && `, ${res.people_added.length} added`}
            </p>
            {res.errors.map((e) => (
              <p key={e} className="mt-1 text-xs text-amber-200">
                {e}
              </p>
            ))}
          </div>
        )}
      </Card>
    </>
  );
}
