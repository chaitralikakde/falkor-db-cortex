"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { NotionDatabase, NotionStatus } from "@/lib/types";
import { useDesk } from "../DeskProvider";
import { Badge, Button, Card, ErrorLine, Field, Input, PageHeader, Segmented, Toggle } from "../ui";

export default function NotionPage({ onBack }: { onBack: () => void }) {
  const { company } = useDesk();
  const [status, setStatus] = useState<NotionStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!company) return;
    setStatus(await api.notion(company.id));
  }, [company]);

  useEffect(() => {
    setStatus(null);
    setError(null);
    load().catch((e) => setError(e.message));
  }, [load]);

  return (
    <div className="h-full overflow-y-auto">
      <PageHeader title="Notion" right={<Button onClick={onBack}>← Connectors</Button>} />
      <div className="mx-auto max-w-3xl space-y-4 p-5">
        <ErrorLine message={error} />
        {status === null && !error && <p className="text-sm text-muted">Loading…</p>}
        {status && !status.connected && <Connect status={status} onDone={setStatus} />}
        {status?.connected && <Connected status={status} onChange={setStatus} />}
      </div>
    </div>
  );
}

function Connect({ status, onDone }: { status: NotionStatus; onDone: (s: NotionStatus) => void }) {
  const { company } = useDesk();
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState<"env" | "token" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const connect = async (useEnv: boolean) => {
    if (!company) return;
    setBusy(useEnv ? "env" : "token");
    setError(null);
    try {
      onDone(await api.connectNotion(company.id, useEnv ? "" : token.trim(), useEnv));
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
            <p className="text-sm">Server token {status.env_hint}</p>
            <Button variant="primary" onClick={() => connect(true)} disabled={busy !== null}>
              {busy === "env" ? "Checking…" : "Use it"}
            </Button>
          </div>
        )}
        <Field label="Internal integration token">
          <Input
            type="password"
            autoComplete="off"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && token.trim() && connect(false)}
            placeholder="ntn_… or secret_…"
          />
        </Field>
        <Button variant="primary" onClick={() => connect(false)} disabled={busy !== null || !token.trim()}>
          {busy === "token" ? "Checking…" : "Connect"}
        </Button>
      </div>
    </Card>
  );
}

function Connected({ status, onChange }: { status: NotionStatus; onChange: (s: NotionStatus) => void }) {
  const { company, refreshGraph } = useDesk();
  const [databases, setDatabases] = useState<NotionDatabase[] | null>(null);
  const [filter, setFilter] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadDatabases = useCallback(async () => {
    if (!company) return;
    try {
      setDatabases(await api.notionDatabases(company.id));
    } catch (e) {
      setError((e as Error).message);
      setDatabases((cur) => cur ?? []);
    }
  }, [company]);

  useEffect(() => {
    loadDatabases();
  }, [loadDatabases]);

  const picked = useMemo(() => new Set(status.databases), [status.databases]);
  const shown = useMemo(() => {
    const q = filter.trim().toLowerCase();
    return (databases ?? [])
      .filter((d) => d.name.toLowerCase().includes(q))
      .sort((a, b) => Number(picked.has(b.id)) - Number(picked.has(a.id)));
  }, [databases, filter, picked]);

  const act = async (key: string, fn: () => Promise<NotionStatus>) => {
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
            <span className="font-medium">{status.workspace || status.name || "Notion"}</span>
            {status.workspace && status.name && status.workspace !== status.name && (
              <span className="text-muted"> · {status.name}</span>
            )}
          </p>
          <Button
            variant="danger"
            disabled={busy !== null}
            onClick={() => {
              if (!company || !confirm("Disconnect Notion?")) return;
              act("disconnect", () => api.disconnectNotion(company.id));
            }}
          >
            Disconnect
          </Button>
        </div>
      </Card>

      <Card title="Databases" right={<span className="text-xs text-muted">{status.databases.length} selected</span>}>
        <div className="mb-2 flex items-center gap-2">
          <Input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter" aria-label="Filter databases" />
          <Button onClick={loadDatabases} disabled={busy !== null} className="shrink-0">
            Refresh
          </Button>
        </div>
        {databases === null ? (
          <p className="text-sm text-muted">Loading…</p>
        ) : shown.length === 0 ? (
          <p className="rounded-lg border border-line px-3 py-3 text-sm text-muted">
            {databases.length === 0 ? "No databases. Share them with the integration." : "No match"}
          </p>
        ) : (
          <ul className="max-h-96 divide-y divide-line overflow-y-auto rounded-lg border border-line">
            {shown.map((d) => (
              <li key={d.id} className="flex items-center gap-3 px-3 py-2">
                <span className="min-w-0 flex-1 truncate text-sm font-medium">{d.name}</span>
                <Toggle
                  on={picked.has(d.id)}
                  label={`Sync ${d.name}`}
                  disabled={busy === d.id || (!picked.has(d.id) && status.databases.length >= 25)}
                  onChange={(v) => {
                    if (!company) return;
                    const next = v ? [...status.databases, d.id] : status.databases.filter((id) => id !== d.id);
                    act(d.id, () => api.patchNotion(company.id, { databases: next }));
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
            <span className="text-sm">Pages per database</span>
            <Segmented
              options={status.page_limits.map((n) => ({ id: String(n), label: String(n) }))}
              value={String(status.page_limit)}
              onChange={(v) => company && act("limit", () => api.patchNotion(company.id, { page_limit: Number(v) }))}
            />
          </div>
          <Button
            variant="primary"
            onClick={async () => {
              if (!company) return;
              if (await act("sync", () => api.syncNotion(company.id))) await refreshGraph().catch(() => {});
            }}
            disabled={busy !== null || status.databases.length === 0 || status.token_missing}
          >
            {busy === "sync" ? "Syncing…" : "Sync now"}
          </Button>
        </div>
        {res && (
          <div className="mt-3 rounded-lg border border-line bg-background p-3 text-sm">
            <p className="text-xs text-muted">{res.at}</p>
            <p className="mt-1">
              {res.databases} databases, {res.docs} pages
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
