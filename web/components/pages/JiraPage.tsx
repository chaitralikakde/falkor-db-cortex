"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { JiraProject, JiraStatus } from "@/lib/types";
import { useDesk } from "../DeskProvider";
import { Badge, Button, Card, ErrorLine, Field, Input, PageHeader, Segmented, Toggle } from "../ui";

export default function JiraPage({ onBack }: { onBack: () => void }) {
  const { company } = useDesk();
  const [status, setStatus] = useState<JiraStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!company) return;
    setStatus(await api.jira(company.id));
  }, [company]);

  useEffect(() => {
    setStatus(null);
    setError(null);
    load().catch((e) => setError(e.message));
  }, [load]);

  return (
    <div className="h-full overflow-y-auto">
      <PageHeader title="Jira" right={<Button onClick={onBack}>← Connectors</Button>} />
      <div className="mx-auto max-w-3xl space-y-4 p-5">
        <ErrorLine message={error} />
        {status === null && !error && <p className="text-sm text-muted">Loading…</p>}
        {status && !status.connected && <Connect status={status} onDone={setStatus} />}
        {status?.connected && <Connected status={status} onChange={setStatus} />}
      </div>
    </div>
  );
}

function Connect({ status, onDone }: { status: JiraStatus; onDone: (s: JiraStatus) => void }) {
  const { company } = useDesk();
  const [site, setSite] = useState(status.env_site);
  const [email, setEmail] = useState("");
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState<"env" | "token" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const connect = async (useEnv: boolean) => {
    if (!company) return;
    setBusy(useEnv ? "env" : "token");
    setError(null);
    try {
      onDone(await api.connectJira(company.id, {
        site: useEnv ? "" : site.trim(),
        email: useEnv ? "" : email.trim(),
        token: useEnv ? "" : token.trim(),
        use_env: useEnv,
      }));
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
            <p className="text-sm">
              Server token {status.env_hint}
              {status.env_site && <span className="text-muted"> · {status.env_site}</span>}
            </p>
            <Button variant="primary" onClick={() => connect(true)} disabled={busy !== null}>
              {busy === "env" ? "Checking…" : "Use it"}
            </Button>
          </div>
        )}
        <Field label="Site">
          <Input value={site} onChange={(e) => setSite(e.target.value)} placeholder="https://your-team.atlassian.net" />
        </Field>
        <Field label="Email">
          <Input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" autoComplete="off" />
        </Field>
        <Field label="API token">
          <Input
            type="password"
            autoComplete="off"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && token.trim() && connect(false)}
            placeholder="Atlassian API token"
          />
        </Field>
        <Button
          variant="primary"
          onClick={() => connect(false)}
          disabled={busy !== null || !site.trim() || !email.trim() || !token.trim()}
        >
          {busy === "token" ? "Checking…" : "Connect"}
        </Button>
      </div>
    </Card>
  );
}

function Connected({ status, onChange }: { status: JiraStatus; onChange: (s: JiraStatus) => void }) {
  const { company, refreshGraph } = useDesk();
  const [projects, setProjects] = useState<JiraProject[] | null>(null);
  const [filter, setFilter] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadProjects = useCallback(async () => {
    if (!company) return;
    try {
      setProjects(await api.jiraProjects(company.id));
    } catch (e) {
      setError((e as Error).message);
      setProjects((cur) => cur ?? []);
    }
  }, [company]);

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  const picked = useMemo(() => new Set(status.projects), [status.projects]);
  const shown = useMemo(() => {
    const q = filter.trim().toLowerCase();
    return (projects ?? [])
      .filter((p) => p.key.toLowerCase().includes(q) || p.name.toLowerCase().includes(q))
      .sort((a, b) => Number(picked.has(b.key)) - Number(picked.has(a.key)));
  }, [projects, filter, picked]);

  const act = async (key: string, fn: () => Promise<JiraStatus>) => {
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
            <span className="font-medium">{status.name || status.email}</span>{" "}
            <span className="text-muted">{status.email}</span>
            <span className="mt-0.5 block text-xs text-muted">{status.site}</span>
          </p>
          <Button
            variant="danger"
            disabled={busy !== null}
            onClick={() => {
              if (!company || !confirm("Disconnect Jira?")) return;
              act("disconnect", () => api.disconnectJira(company.id));
            }}
          >
            Disconnect
          </Button>
        </div>
      </Card>

      <Card title="Projects" right={<span className="text-xs text-muted">{status.projects.length} selected</span>}>
        <div className="mb-2 flex items-center gap-2">
          <Input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter" aria-label="Filter projects" />
          <Button onClick={loadProjects} disabled={busy !== null} className="shrink-0">
            Refresh
          </Button>
        </div>
        {projects === null ? (
          <p className="text-sm text-muted">Loading…</p>
        ) : shown.length === 0 ? (
          <p className="rounded-lg border border-line px-3 py-3 text-sm text-muted">
            {projects.length === 0 ? "No projects" : "No match"}
          </p>
        ) : (
          <ul className="max-h-96 divide-y divide-line overflow-y-auto rounded-lg border border-line">
            {shown.map((p) => (
              <li key={p.key} className="flex items-center gap-3 px-3 py-2">
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">{p.key}</span>
                  <span className="block truncate text-xs text-muted">{p.name}</span>
                </span>
                <Toggle
                  on={picked.has(p.key)}
                  label={`Sync ${p.key}`}
                  disabled={busy === p.key || (!picked.has(p.key) && status.projects.length >= 25)}
                  onChange={(v) => {
                    if (!company) return;
                    const next = v ? [...status.projects, p.key] : status.projects.filter((k) => k !== p.key);
                    act(p.key, () => api.patchJira(company.id, { projects: next }));
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
            <span className="text-sm">Issues per project</span>
            <Segmented
              options={status.issue_limits.map((n) => ({ id: String(n), label: String(n) }))}
              value={String(status.issue_limit)}
              onChange={(v) => company && act("limit", () => api.patchJira(company.id, { issue_limit: Number(v) }))}
            />
          </div>
          <Button
            variant="primary"
            onClick={async () => {
              if (!company) return;
              if (await act("sync", () => api.syncJira(company.id))) await refreshGraph().catch(() => {});
            }}
            disabled={busy !== null || status.projects.length === 0 || status.token_missing}
          >
            {busy === "sync" ? "Syncing…" : "Sync now"}
          </Button>
        </div>
        {res && (
          <div className="mt-3 rounded-lg border border-line bg-background p-3 text-sm">
            <p className="text-xs text-muted">{res.at}</p>
            <p className="mt-1">
              {res.projects} projects, {res.tickets} tickets
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
