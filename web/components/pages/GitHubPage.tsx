"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { GitHubRepo, GitHubStatus } from "@/lib/types";
import { useDesk } from "../DeskProvider";
import { Badge, Button, Card, ErrorLine, Field, Input, PageHeader, Segmented, Toggle } from "../ui";

/** Manage GitHub from the dashboard: connect a token, pick repositories, sync pull requests into the graph. */
export default function GitHubPage({ onBack }: { onBack: () => void }) {
  const { company } = useDesk();
  const [status, setStatus] = useState<GitHubStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!company) return;
    setStatus(await api.github(company.id));
  }, [company]);

  useEffect(() => {
    setStatus(null);
    setError(null);
    load().catch((e) => setError(e.message));
  }, [load]);

  return (
    <div className="h-full overflow-y-auto">
      <PageHeader
        title="GitHub"
        subtitle="Repositories and pull requests become graph evidence: who wrote and reviewed what. GitHub never sets an owner."
        right={<Button onClick={onBack}>← Connectors</Button>}
      />
      <div className="mx-auto max-w-3xl space-y-4 p-5">
        <ErrorLine message={error} />
        {status === null && !error && <p className="text-sm text-muted">Loading…</p>}
        {status && !status.connected && <Connect status={status} onDone={setStatus} />}
        {status?.connected && <Connected status={status} onChange={setStatus} />}
      </div>
    </div>
  );
}

function Connect({ status, onDone }: { status: GitHubStatus; onDone: (s: GitHubStatus) => void }) {
  const { company } = useDesk();
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState<"env" | "token" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const connect = async (useEnv: boolean) => {
    if (!company) return;
    setBusy(useEnv ? "env" : "token");
    setError(null);
    try {
      onDone(await api.connectGitHub(company.id, useEnv ? "" : token.trim(), useEnv));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <Card title="Connect GitHub">
      <div className="space-y-4">
        <ErrorLine message={error} />
        {status.env_available && (
          <div className="flex items-center justify-between gap-3 rounded-lg border border-line bg-background px-3 py-2.5">
            <div>
              <p className="text-sm font-medium">Use the token set on the server</p>
              <p className="text-xs text-muted">
                <code>GITHUB_TOKEN</code> {status.env_hint}. It stays on the server and is never sent to the browser.
              </p>
            </div>
            <Button variant="primary" onClick={() => connect(true)} disabled={busy !== null} className="shrink-0">
              {busy === "env" ? "Checking…" : "Use it"}
            </Button>
          </div>
        )}

        <div className="space-y-2">
          <p className="text-sm text-muted">
            {status.env_available ? "Or paste a token for this company." : "Paste a personal access token."}{" "}
            <a href="https://github.com/settings/tokens" target="_blank" rel="noreferrer" className="text-accent hover:underline">
              Create one ↗
            </a>
          </p>
          <Field label="Personal access token">
            <div className="flex gap-2">
              <Input
                type="password"
                autoComplete="off"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && token.trim() && connect(false)}
                placeholder="ghp_… or github_pat_…"
              />
              <Button onClick={() => connect(false)} disabled={busy !== null || !token.trim()} className="shrink-0">
                {busy === "token" ? "Checking…" : "Connect"}
              </Button>
            </div>
          </Field>
          <p className="text-xs text-muted">
            Read access is enough: a classic token with <code>repo</code> (or <code>public_repo</code> for public repositories only), or a
            fine-grained token with read-only Metadata and Pull requests. The token is checked with GitHub, then stored on the server and
            never shown again.
          </p>
        </div>
      </div>
    </Card>
  );
}

function Connected({ status, onChange }: { status: GitHubStatus; onChange: (s: GitHubStatus) => void }) {
  const { company, refreshGraph } = useDesk();
  const [repos, setRepos] = useState<GitHubRepo[] | null>(null);
  const [filter, setFilter] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadRepos = useCallback(async () => {
    if (!company) return;
    try {
      setRepos(await api.githubRepos(company.id));
    } catch (e) {
      setError((e as Error).message);
      setRepos((cur) => cur ?? []);
    }
  }, [company]);

  useEffect(() => {
    loadRepos();
  }, [loadRepos]);

  const picked = useMemo(() => new Set(status.repos), [status.repos]);

  const shown = useMemo(() => {
    const q = filter.trim().toLowerCase();
    return (repos ?? [])
      .filter((r) => r.full_name.toLowerCase().includes(q))
      .sort((a, b) => Number(picked.has(b.full_name)) - Number(picked.has(a.full_name)));
  }, [repos, filter, picked]);

  const act = async (key: string, fn: () => Promise<GitHubStatus>) => {
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

  const toggle = (r: GitHubRepo, on: boolean) => {
    if (!company) return;
    const next = on ? [...status.repos, r.full_name] : status.repos.filter((n) => n !== r.full_name);
    return act(r.full_name, () => api.patchGitHub(company.id, { repos: next }));
  };

  const sync = async () => {
    if (!company) return;
    if (await act("sync", () => api.syncGitHub(company.id))) await refreshGraph().catch(() => {});
  };

  const res = status.last_result;

  return (
    <>
      <ErrorLine message={error} />

      <Card title="Account" right={<Badge tone={status.token_missing ? "warn" : "ok"}>{status.token_missing ? "token missing" : "connected"}</Badge>}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="text-sm">
            <p>
              <span className="font-medium">{status.name || status.login}</span>{" "}
              <span className="font-mono text-muted">@{status.login}</span>
            </p>
            <p className="mt-0.5 text-xs text-muted">
              {status.source === "server" ? "Using the token set on the server" : "Using a token you pasted"} {status.token_hint}
              {status.scopes.length > 0 && ` · scopes: ${status.scopes.slice(0, 4).join(", ")}${status.scopes.length > 4 ? ` +${status.scopes.length - 4}` : ""}`}
            </p>
          </div>
          <Button
            variant="danger"
            disabled={busy !== null}
            onClick={() => {
              if (!company || !confirm("Disconnect GitHub? Facts already in the graph stay. A pasted token is erased.")) return;
              act("disconnect", () => api.disconnectGitHub(company.id));
            }}
          >
            Disconnect
          </Button>
        </div>
        {status.scopes.some((s) => s.startsWith("admin:") || s.startsWith("delete")) && (
          <p className="mt-3 text-xs text-amber-200">
            This token can do much more than read. Cortex only reads, but a read-only token is safer to keep on a server.
          </p>
        )}
      </Card>

      <Card
        title="Repositories"
        right={<span className="text-xs text-muted">{status.repos.length} selected</span>}
      >
        <div className="mb-2 flex items-center gap-2">
          <Input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter repositories" aria-label="Filter repositories" />
          <Button onClick={loadRepos} disabled={busy !== null} className="shrink-0">
            Refresh
          </Button>
        </div>
        {repos === null ? (
          <p className="text-sm text-muted">Loading from GitHub…</p>
        ) : shown.length === 0 ? (
          <p className="rounded-lg border border-line px-3 py-4 text-center text-sm text-muted">
            {repos.length === 0 ? "This token cannot see any repositories." : "No repository matches that filter."}
          </p>
        ) : (
          <ul className="max-h-96 divide-y divide-line overflow-y-auto rounded-lg border border-line">
            {shown.slice(0, 200).map((r) => (
              <li key={r.full_name} className="flex items-center gap-3 px-3 py-2">
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2 text-sm">
                    <span className="truncate">{r.full_name}</span>
                    {r.private && <Badge>private</Badge>}
                    {r.archived && <Badge>archived</Badge>}
                    {r.fork && <Badge>fork</Badge>}
                  </span>
                  <span className="block truncate text-xs text-muted">
                    {[r.language, r.pushed && `pushed ${r.pushed}`, r.description].filter(Boolean).join(" · ")}
                  </span>
                </span>
                <Toggle
                  on={picked.has(r.full_name)}
                  label={`Sync ${r.full_name}`}
                  disabled={busy === r.full_name || (!picked.has(r.full_name) && status.repos.length >= 25)}
                  onChange={(v) => toggle(r, v)}
                />
              </li>
            ))}
          </ul>
        )}
        <p className="mt-1.5 text-xs text-muted">Pick up to 25 repositories. Selected ones are listed first.</p>
      </Card>

      <Card title="Sync">
        <div className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <span className="text-sm">Latest pull requests per repository</span>
              <Segmented
                options={status.pr_limits.map((n) => ({ id: String(n), label: String(n) }))}
                value={String(status.pr_limit)}
                onChange={(v) => company && act("limit", () => api.patchGitHub(company.id, { pr_limit: Number(v) }))}
              />
            </div>
            <Button variant="primary" onClick={sync} disabled={busy !== null || status.repos.length === 0 || status.token_missing}>
              {busy === "sync" ? "Syncing…" : "Sync now"}
            </Button>
          </div>

          {status.repos.length === 0 && <p className="text-sm text-muted">Select at least one repository above, then sync.</p>}

          {res && (
            <div className="rounded-lg border border-line bg-background p-3 text-sm">
              <p className="text-xs text-muted">Last sync {res.at}</p>
              <p className="mt-1">
                {res.repos} {res.repos === 1 ? "repository" : "repositories"}, {res.prs} pull requests, {res.people_linked} people matched
                {res.people_added.length > 0 && `, ${res.people_added.length} added`}.
              </p>
              {res.people_added.length > 0 && (
                <p className="mt-1 text-xs text-muted">
                  Added as people with no team or owner role: {res.people_added.slice(0, 8).map((p) => `@${p}`).join(", ")}
                  {res.people_added.length > 8 && ` +${res.people_added.length - 8} more`}.
                </p>
              )}
              {res.errors.map((e) => (
                <p key={e} className="mt-1 text-xs text-amber-200">
                  {e}
                </p>
              ))}
            </div>
          )}
          <p className="text-xs text-muted">
            A sync adds repositories, pull requests, authors and reviewers, matching people by their GitHub login. It never creates an OWNS
            link: only Apply on the Graph page does that. Running it again changes nothing that is already there.
          </p>
        </div>
      </Card>
    </>
  );
}
