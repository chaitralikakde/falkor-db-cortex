"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Department, SlackBot, SlackChannelRow, SlackStatus } from "@/lib/types";
import { useDesk } from "../DeskProvider";
import { Button, ErrorLine, Input, Toggle } from "../ui";

export default function SlackBotCard({
  bot,
  departments,
  open,
  onOpen,
  onChange,
}: {
  bot: SlackBot;
  departments: Department[];
  open: boolean;
  onOpen: () => void;
  onChange: (s: SlackStatus) => void;
}) {
  const { company } = useDesk();
  const [joinable, setJoinable] = useState<SlackChannelRow[] | null>(null);
  const [pick, setPick] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [label, setLabel] = useState(bot.label);

  const loadJoinable = useCallback(async () => {
    if (!company) return;
    try {
      const r = await api.slackChannels(company.id, bot.id);
      setJoinable(r.channels.filter((c) => c.kind === "public" && !c.member));
    } catch (e) {
      setError((e as Error).message);
      setJoinable([]);
    }
  }, [company, bot.id]);

  useEffect(() => {
    if (!open) return;
    setLabel(bot.label);
    loadJoinable();
  }, [open, bot.id, bot.label, loadJoinable]);

  const act = async (key: string, fn: () => Promise<SlackStatus>) => {
    setBusy(key);
    setError(null);
    try {
      onChange(await fn());
      if (open) await loadJoinable();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const deptName = departments.find((d) => d.id === bot.department)?.name ?? (bot.department ? bot.department : "All");
  const listening = bot.channels.filter((c) => c.listening && !c.im);
  const inChannels = bot.channels.filter((c) => !c.im);

  return (
    <div>
      <button
        type="button"
        onClick={onOpen}
        className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-panel-2/60"
      >
        <span className={`h-2 w-2 shrink-0 rounded-full ${bot.error ? "bg-amber-400" : bot.running ? "bg-emerald-400" : "bg-muted"}`} />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium">{bot.label}</span>
          <span className="block truncate text-xs text-muted">@{bot.bot_user}</span>
        </span>
        <span className="hidden text-xs text-muted sm:block">{deptName}</span>
        <span className="max-w-[40%] truncate text-xs text-muted">
          {listening.length ? listening.map((c) => `#${c.name}`).join(" · ") : "not listening"}
        </span>
        <span className="text-xs text-muted">{open ? "▾" : "›"}</span>
      </button>

      {open && (
        <div className="space-y-4 border-t border-line bg-background/40 px-4 py-3">
          <ErrorLine message={error} />
          {bot.error && <p className="text-sm text-amber-200">{bot.error}</p>}

          <div className="flex flex-wrap items-end gap-2">
            <label className="text-xs text-muted">
              Name
              <Input value={label} onChange={(e) => setLabel(e.target.value)} className="mt-1 w-44" />
            </label>
            <label className="text-xs text-muted">
              Department
              <select
                value={bot.department}
                disabled={busy !== null}
                onChange={(e) => company && act("dept", () => api.patchSlackBot(company.id, bot.id, { department: e.target.value }))}
                className="mt-1 block w-48 rounded-lg border border-line bg-background px-3 py-2 text-sm outline-none focus:border-accent/70"
              >
                <option value="">Whole company</option>
                {departments.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
              </select>
            </label>
            {label.trim() && label.trim() !== bot.label && (
              <Button
                variant="primary"
                disabled={busy !== null}
                onClick={() => company && act("rename", () => api.patchSlackBot(company.id, bot.id, { label: label.trim() }))}
              >
                Save name
              </Button>
            )}
          </div>

          <div>
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">Answers in</p>
            {inChannels.length === 0 ? (
              <p className="text-sm text-muted">Not in a channel yet. Join one below, or /invite in Slack.</p>
            ) : (
              <ul className="space-y-1">
                {inChannels.map((c) => (
                  <li key={c.id} className="flex items-center gap-3 py-1">
                    <span className="min-w-0 flex-1 truncate text-sm">#{c.name}</span>
                    <Toggle
                      on={c.listening}
                      label={`Answer in ${c.name}`}
                      disabled={busy === c.id}
                      onChange={(v) => company && act(c.id, () => api.listenSlackChannel(company.id, bot.id, c.id, v))}
                    />
                    <button
                      className="text-xs text-muted hover:text-red-300 disabled:opacity-40"
                      disabled={busy === c.id}
                      onClick={() => {
                        if (company && confirm(`Leave #${c.name}?`)) act(c.id, () => api.leaveSlackChannel(company.id, bot.id, c.id));
                      }}
                    >
                      Leave
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <div className="mt-2 flex items-center gap-2">
              <select
                value={pick}
                onChange={(e) => setPick(e.target.value)}
                className="min-w-0 flex-1 rounded-lg border border-line bg-background px-3 py-1.5 text-sm outline-none focus:border-accent/70"
              >
                <option value="">{joinable === null ? "Loading channels…" : "Join a channel"}</option>
                {(joinable ?? []).map((c) => (
                  <option key={c.id} value={c.id}>
                    #{c.name}
                  </option>
                ))}
              </select>
              <Button
                disabled={!pick || busy !== null}
                onClick={() => {
                  if (!company || !pick) return;
                  const id = pick;
                  setPick("");
                  act(id, () => api.joinSlackChannel(company.id, bot.id, id));
                }}
              >
                Join
              </Button>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-5">
            <label className="flex items-center gap-2 text-sm">
              <Toggle
                on={bot.settings.thread}
                label="Thread"
                disabled={busy === "settings"}
                onChange={(v) => company && act("settings", () => api.patchSlackBot(company.id, bot.id, { settings: { thread: v } }))}
              />
              Thread
            </label>
            <label className="flex items-center gap-2 text-sm">
              <Toggle
                on={bot.settings.sources}
                label="Sources"
                disabled={busy === "settings"}
                onChange={(v) => company && act("settings", () => api.patchSlackBot(company.id, bot.id, { settings: { sources: v } }))}
              />
              Sources
            </label>
            <Button
              variant="danger"
              className="ml-auto"
              disabled={busy === "remove"}
              onClick={() => {
                if (!company || !confirm(`Remove “${bot.label}”?`)) return;
                act("remove", () => api.removeSlackBot(company.id, bot.id));
              }}
            >
              Remove
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
