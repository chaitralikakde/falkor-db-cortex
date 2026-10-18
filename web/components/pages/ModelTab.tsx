"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { ModelConfig, Provider } from "@/lib/types";
import { useDesk } from "../DeskProvider";
import { Badge, Button, Card, ErrorLine, Field, Input } from "../ui";

type Check = { ok: boolean; text: string } | null;

/** Pick a provider, paste a key, Test, Save. The key is sent once and never comes back. */
export default function ModelTab() {
  const { company } = useDesk();
  const [providers, setProviders] = useState<Provider[]>([]);
  const [saved, setSaved] = useState<ModelConfig | null>(null);

  const [provider, setProvider] = useState("openrouter");
  const [model, setModel] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [models, setModels] = useState<string[]>([]);

  const [busy, setBusy] = useState<"test" | "save" | "models" | "off" | null>(null);
  const [check, setCheck] = useState<Check>(null);
  const [error, setError] = useState<string | null>(null);
  const [justSaved, setJustSaved] = useState(false);

  const current = providers.find((p) => p.id === provider);

  // load providers and what is already saved for this company
  useEffect(() => {
    if (!company) return;
    setApiKey("");
    setCheck(null);
    setModels([]);
    Promise.all([api.providers(), api.settings(company.id)])
      .then(([provs, s]) => {
        setProviders(provs);
        setSaved(s.model);
        if (s.model.provider !== "none") {
          setProvider(s.model.provider);
          setModel(s.model.model);
          setBaseUrl(s.model.base_url);
        } else {
          setProvider("openrouter");
          setModel("");
          setBaseUrl("");
        }
      })
      .catch((e) => setError(e.message));
  }, [company]);

  const draft = useCallback(
    () => ({ provider, model, base_url: baseUrl, api_key: apiKey }),
    [provider, model, baseUrl, apiKey],
  );

  const pick = (id: string) => {
    if (id === provider) return;
    setProvider(id);
    setModel("");
    setBaseUrl("");
    setApiKey("");
    setModels([]);
    setCheck(null);
  };

  const loadModels = async () => {
    if (!company) return;
    setBusy("models");
    try {
      const r = await api.listModels(company.id, draft());
      setModels(r.models);
      if (r.error) setCheck({ ok: false, text: `Could not load models: ${r.error}` });
    } finally {
      setBusy(null);
    }
  };

  const test = async () => {
    if (!company) return;
    setBusy("test");
    setCheck(null);
    setError(null);
    try {
      const r = await api.testModel(company.id, { ...draft(), model: model || current?.default_model || "" });
      setCheck(r.ok ? { ok: true, text: `Connected. The model replied "${r.reply}" in ${r.ms} ms.` } : { ok: false, text: r.message ?? "Failed." });
      if (r.ok && models.length === 0) loadModels();
    } catch (e) {
      setCheck({ ok: false, text: (e as Error).message });
    } finally {
      setBusy(null);
    }
  };

  const save = async () => {
    if (!company) return;
    setBusy("save");
    setError(null);
    try {
      const m = await api.saveModel(company.id, { ...draft(), model: model || current?.default_model || "" });
      setSaved(m);
      setModel(m.model);
      setApiKey("");
      setJustSaved(true);
      setTimeout(() => setJustSaved(false), 2000);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const disconnect = async () => {
    if (!company || !confirm("Disconnect the model and erase the stored key?")) return;
    setBusy("off");
    try {
      setSaved(await api.disconnectModel(company.id));
      setApiKey("");
      setCheck(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const sameProvider = saved?.provider === provider;
  const hasStoredKey = sameProvider && saved?.has_key;
  const needsKey = !current?.no_key;
  const canTest = !!current && (!needsKey || !!apiKey || hasStoredKey) && (provider !== "custom" || !!baseUrl);

  return (
    <>
      <ErrorLine message={error} />

      <Card
        title="Language model"
        right={
          saved?.connected ? <Badge tone="ok">connected · {saved.label}</Badge> : <Badge>rule-based, no model connected</Badge>
        }
      >
        <p className="mb-4 text-sm text-muted">
          A model reads the documents you upload and finds facts the built-in rules miss. Every fact it returns must quote a
          sentence from the file, or it is dropped. Without a model, everything still works by rules.
        </p>

        <div className="space-y-4">
          <div>
            <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-muted">Provider</span>
            <div className="flex flex-wrap gap-2">
              {providers.map((p) => (
                <button
                  key={p.id}
                  onClick={() => pick(p.id)}
                  className={`rounded-lg border px-3 py-1.5 text-sm transition ${
                    provider === p.id
                      ? "border-accent bg-accent/10 text-foreground"
                      : "border-line text-muted hover:border-[#3a4a5e] hover:text-foreground"
                  }`}
                >
                  {p.name}
                  {p.recommended && <span className="ml-1.5 text-[10px] uppercase tracking-wide text-accent">easiest</span>}
                </button>
              ))}
            </div>
            {current?.note && <p className="mt-2 text-xs text-muted">{current.note}</p>}
          </div>

          {needsKey && (
            <Field label="API key">
              <Input
                type="password"
                autoComplete="off"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={hasStoredKey ? `Saved ${saved?.key_hint}. Leave blank to keep it.` : "Paste your key"}
              />
              {current?.key_url && (
                <a
                  href={current.key_url}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-1 inline-block text-xs text-accent hover:underline"
                >
                  Get a {current.name} key ↗
                </a>
              )}
            </Field>
          )}

          {(provider === "custom" || provider === "ollama") && (
            <Field label="Base URL" hint="Must end where /chat/completions begins, for example http://localhost:11434/v1">
              <Input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder={current?.base_url || "https://…/v1"} />
            </Field>
          )}

          <Field label="Model">
            <div className="flex gap-2">
              <Input
                list="model-options"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                placeholder={current?.default_model || "model name"}
              />
              <Button onClick={loadModels} disabled={!canTest || busy === "models"} className="shrink-0">
                {busy === "models" ? "Loading…" : "Load list"}
              </Button>
            </div>
            <datalist id="model-options">
              {models.map((m) => (
                <option key={m} value={m} />
              ))}
            </datalist>
            {models.length > 0 && <span className="mt-1 block text-xs text-muted">{models.length} models available. Start typing to filter.</span>}
          </Field>

          {check && (
            <p
              className={`rounded-lg border px-3 py-2 text-sm ${
                check.ok ? "border-emerald-800/60 bg-emerald-950/30 text-emerald-200" : "border-red-900/60 bg-red-950/40 text-red-300"
              }`}
            >
              {check.text}
            </p>
          )}

          <div className="flex flex-wrap items-center gap-2">
            <Button onClick={test} disabled={!canTest || busy === "test"}>
              {busy === "test" ? "Testing…" : "Test connection"}
            </Button>
            <Button variant="primary" onClick={save} disabled={!current || busy === "save" || (needsKey && !apiKey && !hasStoredKey)}>
              {busy === "save" ? "Saving…" : "Save"}
            </Button>
            {justSaved && <span className="text-sm text-emerald-300">Saved</span>}
            {saved?.connected && (
              <Button variant="danger" onClick={disconnect} disabled={busy === "off"} className="ml-auto">
                Disconnect
              </Button>
            )}
          </div>
        </div>
      </Card>

      <p className="text-xs text-muted">
        The key is stored on the server, never shown again and never written to the graph. You can also set{" "}
        <code>MODEL_API_KEY</code> in the server environment instead.
      </p>
    </>
  );
}
