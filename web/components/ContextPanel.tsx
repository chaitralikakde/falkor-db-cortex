"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { UploadResult } from "@/lib/types";
import { useDesk } from "./DeskProvider";
import { Badge, Button, ErrorLine, Field, Input, Segmented, Toggle } from "./ui";

const SAMPLE_FILES = [
  "01-team.md",
  "02-systems-and-owners.md",
  "03-adr-7-billing-uses-postgres.md",
  "04-handoff-note.md",
];

type Mode = "files" | "person";

/**
 * Upload documents or add one person by hand. Everything lands in the company graph,
 * and the new nodes light up on the map for a few seconds.
 */
export default function ContextPanel({ onChanged }: { onChanged?: () => void }) {
  const { company, refreshGraph, setLit, clearLit, setDim } = useDesk();
  const [mode, setMode] = useState<Mode>("files");

  const [picked, setPicked] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [results, setResults] = useState<UploadResult[]>([]);
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const [form, setForm] = useState({ team: "", person: "", role: "", system: "", owner: false });
  const [formNotes, setFormNotes] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setResults([]);
    setFormNotes([]);
    setPicked([]);
    setError(null);
  }, [company?.id]);

  /** Light up what was just written, then fade back to the plain map. */
  const flash = (nodeIds: string[], linkIds: string[]) => {
    setDim(true);
    setLit(nodeIds, linkIds);
    setTimeout(() => {
      setDim(false);
      clearLit();
    }, 4500);
  };

  const doUpload = async (files: File[]) => {
    if (!company || files.length === 0) return;
    setUploading(true);
    setError(null);
    try {
      const { results } = await api.upload(company.id, files);
      setResults((prev) => [...results, ...prev]);
      await refreshGraph();
      onChanged?.();
      flash(
        results.flatMap((r) => r.nodes ?? []).map((n) => n.id),
        results.flatMap((r) => r.links ?? []).map((l) => l.id),
      );
      setPicked([]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setUploading(false);
    }
  };

  const loadSamples = async () => {
    const files = await Promise.all(
      SAMPLE_FILES.map(async (name) => {
        const res = await fetch(`/sample-upload/${name}`);
        return new File([await res.blob()], name, { type: "text/markdown" });
      }),
    );
    await doUpload(files);
  };

  const submitForm = async () => {
    if (!company || !form.person.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const r = await api.form(company.id, form);
      setFormNotes(r.notes);
      await refreshGraph();
      onChanged?.();
      flash(
        r.nodes.map((n) => n.id),
        r.links.map((l) => l.id),
      );
      setForm({ ...form, person: "", role: "", owner: false });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      <Segmented
        value={mode}
        onChange={setMode}
        options={[
          { id: "files", label: "Upload files" },
          { id: "person", label: "Add a person" },
        ]}
      />
      <ErrorLine message={error} />

      {mode === "files" && (
        <div className="space-y-3">
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              setPicked((p) => [...p, ...Array.from(e.dataTransfer.files)]);
            }}
            onClick={() => fileInput.current?.click()}
            className={`cursor-pointer rounded-xl border border-dashed px-4 py-7 text-center transition ${
              dragging ? "border-accent bg-accent/5" : "border-line hover:border-[#3a4a5e]"
            }`}
          >
            <p className="text-sm">Drop files here, or click to choose</p>
            <p className="mt-1 text-xs text-muted">Markdown, text or PDF</p>
            <input
              ref={fileInput}
              type="file"
              multiple
              accept=".md,.markdown,.txt,.pdf"
              className="hidden"
              onChange={(e) => {
                setPicked((p) => [...p, ...Array.from(e.target.files ?? [])]);
                e.target.value = "";
              }}
            />
          </div>

          {picked.length > 0 && (
            <div className="space-y-2">
              <ul className="space-y-1 text-sm">
                {picked.map((f, i) => (
                  <li key={f.name + i} className="flex items-center justify-between rounded-lg bg-background px-3 py-1.5">
                    <span className="truncate">{f.name}</span>
                    <button
                      className="text-xs text-muted hover:text-foreground"
                      onClick={() => setPicked(picked.filter((_, j) => j !== i))}
                    >
                      remove
                    </button>
                  </li>
                ))}
              </ul>
              <Button variant="primary" disabled={uploading} onClick={() => doUpload(picked)} className="w-full">
                {uploading ? "Mapping…" : `Map ${picked.length} file${picked.length > 1 ? "s" : ""}`}
              </Button>
            </div>
          )}

          {picked.length === 0 && (
            <button
              onClick={loadSamples}
              disabled={uploading || !company}
              className="text-xs text-muted underline-offset-2 hover:text-accent hover:underline disabled:opacity-40"
            >
              {uploading ? "Mapping…" : "No files handy? Try 4 sample files"}
            </button>
          )}

          {results.length > 0 && (
            <ul className="space-y-2">
              {results.map((r, i) => (
                <ResultRow key={r.file + i} r={r} />
              ))}
            </ul>
          )}
        </div>
      )}

      {mode === "person" && (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <Field label="Person">
              <Input value={form.person} placeholder="Priya Shah" onChange={(e) => setForm({ ...form, person: e.target.value })} />
            </Field>
            <Field label="Role">
              <Input value={form.role} placeholder="Eng lead" onChange={(e) => setForm({ ...form, role: e.target.value })} />
            </Field>
            <Field label="Team">
              <Input value={form.team} placeholder="Engineering" onChange={(e) => setForm({ ...form, team: e.target.value })} />
            </Field>
            <Field label="System">
              <Input value={form.system} placeholder="Payments API" onChange={(e) => setForm({ ...form, system: e.target.value })} />
            </Field>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <Toggle on={form.owner} onChange={(v) => setForm({ ...form, owner: v })} label="Owner" disabled={!form.system.trim()} />
            This person owns the system
          </label>
          <Button variant="primary" disabled={saving || !form.person.trim()} onClick={submitForm} className="w-full">
            {saving ? "Adding…" : "Add to graph"}
          </Button>
          {formNotes.length > 0 && (
            <ul className="fade-up space-y-0.5 text-sm text-muted">
              {formNotes.map((n, i) => (
                <li key={i}>{n}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function ResultRow({ r }: { r: UploadResult }) {
  const [open, setOpen] = useState(false);
  const notes = r.notes ?? [];
  const shown = open ? notes : notes.slice(0, 3);
  return (
    <li className="fade-up rounded-lg border border-line bg-background p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-sm font-medium">{r.file}</span>
        {r.error ? (
          <Badge tone="warn">skipped</Badge>
        ) : (
          <span className="shrink-0 text-xs text-muted">
            {r.nodes?.length} nodes · {r.links?.length} links
          </span>
        )}
      </div>
      {r.error && <p className="mt-1 text-sm text-red-300">{r.error}</p>}
      {shown.length > 0 && (
        <ul className="mt-2 space-y-0.5 text-xs text-muted">
          {shown.map((n, i) => (
            <li key={i} className={n.startsWith("PROPOSES") ? "text-amber-300" : ""}>
              {n}
            </li>
          ))}
        </ul>
      )}
      {notes.length > 3 && (
        <button onClick={() => setOpen(!open)} className="mt-1 text-xs text-accent hover:underline">
          {open ? "Show less" : `Show ${notes.length - 3} more`}
        </button>
      )}
      {r.tasks && r.tasks.length > 0 && (
        <p className="mt-2 text-xs text-amber-300">
          Handoff proposed. Ownership stays as it is until an admin clicks Apply on Graph.
        </p>
      )}
    </li>
  );
}
