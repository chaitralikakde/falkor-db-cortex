"use client";

import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, TextareaHTMLAttributes } from "react";

export function PageHeader({
  title,
  subtitle,
  right,
}: {
  title: string;
  subtitle?: string;
  right?: ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-0.5 text-sm text-muted">{subtitle}</p>}
      </div>
      {right}
    </div>
  );
}

export function Card({
  title,
  children,
  className = "",
  right,
}: {
  title?: string;
  children: ReactNode;
  className?: string;
  right?: ReactNode;
}) {
  return (
    <section className={`rounded-xl border border-line bg-panel ${className}`}>
      {title && (
        <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
          <h2 className="text-sm font-medium">{title}</h2>
          {right}
        </div>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "ghost" | "danger";
};

export function Button({ variant = "ghost", className = "", ...p }: BtnProps) {
  const styles = {
    primary: "bg-accent text-black hover:brightness-110",
    ghost: "border border-line bg-panel-2 text-foreground hover:border-[#3a4a5e]",
    danger: "border border-red-900/60 bg-red-950/40 text-red-300 hover:bg-red-950/70",
  }[variant];
  return (
    <button
      {...p}
      className={`inline-flex items-center justify-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-40 ${styles} ${className}`}
    />
  );
}

export function Input(p: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...p}
      className={`w-full rounded-lg border border-line bg-background px-3 py-2 text-sm outline-none placeholder:text-muted/70 focus:border-accent/70 ${p.className ?? ""}`}
    />
  );
}

export function Textarea(p: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...p}
      className={`w-full rounded-lg border border-line bg-background px-3 py-2 text-sm outline-none placeholder:text-muted/70 focus:border-accent/70 ${p.className ?? ""}`}
    />
  );
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-muted">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-muted">{hint}</span>}
    </label>
  );
}

export function Toggle({
  on,
  onChange,
  disabled,
  label,
}: {
  on: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
  label?: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!on)}
      className={`relative h-5 w-9 shrink-0 rounded-full transition disabled:opacity-40 ${on ? "bg-accent" : "bg-[#2b3848]"}`}
    >
      <span
        className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all ${on ? "left-[18px]" : "left-0.5"}`}
      />
    </button>
  );
}

export function Badge({ children, tone = "muted" }: { children: ReactNode; tone?: "muted" | "ok" | "warn" }) {
  const tones = {
    muted: "border-line text-muted",
    ok: "border-emerald-800/60 bg-emerald-950/40 text-emerald-300",
    warn: "border-amber-700/60 bg-amber-950/40 text-amber-300",
  }[tone];
  return <span className={`rounded-full border px-2 py-0.5 text-xs ${tones}`}>{children}</span>;
}

export function Tabs<T extends string>({
  tabs,
  value,
  onChange,
}: {
  tabs: { id: T; label: string }[];
  value: T;
  onChange: (id: T) => void;
}) {
  return (
    <div className="flex gap-1 border-b border-line px-5">
      {tabs.map((t) => (
        <button
          key={t.id}
          onClick={() => onChange(t.id)}
          className={`-mb-px border-b-2 px-3 py-2.5 text-sm transition ${
            value === t.id ? "border-accent text-foreground" : "border-transparent text-muted hover:text-foreground"
          }`}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { id: T; label: string }[];
  value: T;
  onChange: (id: T) => void;
}) {
  return (
    <div className="inline-flex rounded-lg border border-line bg-background p-0.5">
      {options.map((o) => (
        <button
          key={o.id}
          onClick={() => onChange(o.id)}
          className={`rounded-md px-3 py-1 text-sm transition ${
            value === o.id ? "bg-panel-2 text-foreground" : "text-muted hover:text-foreground"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function ErrorLine({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p className="rounded-lg border border-red-900/60 bg-red-950/40 px-3 py-2 text-sm text-red-300">
      {message}
    </p>
  );
}

export const KIND_COLOR: Record<string, string> = {
  Person: "#FF6B6B",
  Team: "#4C78D4",
  Project: "#E36AA8",
  System: "#3DAB6E",
  Decision: "#F5A524",
  Repo: "#7A6FF0",
  PullRequest: "#7A6FF0",
  Doc: "#9AA0A6",
  Ticket: "#9AA0A6",
  Message: "#9AA0A6",
  Environment: "#5FB8C9",
  Session: "#F5C16C",
  Finding: "#F5C16C",
  Task: "#F5C16C",
  Agent: "#C792EA",
};

export function Dot({ kind }: { kind: string }) {
  return (
    <span
      className="inline-block h-2.5 w-2.5 shrink-0 rounded-full"
      style={{ background: KIND_COLOR[kind] ?? "#9AA0A6" }}
    />
  );
}
