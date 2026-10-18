"""One small client for every model provider.

OpenRouter, OpenAI, Fireworks, Groq, Gemini, Anthropic and Ollama all accept the same
OpenAI-style `POST {base_url}/chat/completions` request, so a provider is just a base URL.
No SDK needed: plain HTTPS with the standard library.
"""
import json
import os
import re
import time
import urllib.error
import urllib.request

PROVIDERS = [
    {"id": "openrouter", "name": "OpenRouter", "recommended": True,
     "base_url": "https://openrouter.ai/api/v1", "default_model": "anthropic/claude-sonnet-4.5",
     "key_url": "https://openrouter.ai/keys",
     "note": "One key for Claude, GPT, Llama and many more. Easiest to start with."},
    {"id": "openai", "name": "OpenAI", "base_url": "https://api.openai.com/v1",
     "default_model": "gpt-4o-mini", "key_url": "https://platform.openai.com/api-keys"},
    {"id": "fireworks", "name": "Fireworks AI", "base_url": "https://api.fireworks.ai/inference/v1",
     "default_model": "accounts/fireworks/models/llama-v3p3-70b-instruct",
     "key_url": "https://fireworks.ai/account/api-keys"},
    {"id": "anthropic", "name": "Anthropic", "base_url": "https://api.anthropic.com/v1",
     "default_model": "claude-sonnet-4-5", "key_url": "https://console.anthropic.com/settings/keys"},
    {"id": "gemini", "name": "Google Gemini",
     "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
     "default_model": "gemini-2.0-flash", "key_url": "https://aistudio.google.com/apikey"},
    {"id": "groq", "name": "Groq", "base_url": "https://api.groq.com/openai/v1",
     "default_model": "llama-3.3-70b-versatile", "key_url": "https://console.groq.com/keys"},
    {"id": "ollama", "name": "Ollama (local)", "base_url": "http://host.docker.internal:11434/v1",
     "default_model": "llama3.2", "no_key": True,
     "note": "Runs on your machine. No key needed."},
    {"id": "custom", "name": "Custom (OpenAI-compatible)", "base_url": "", "default_model": "",
     "note": "Any server that speaks the OpenAI chat API."},
]
BY_ID = {p["id"]: p for p in PROVIDERS}


class LLMError(Exception):
    pass


def resolve(cfg):
    """(base_url, api_key, model) for a stored or draft config. Raises LLMError if unusable."""
    prov = BY_ID.get((cfg or {}).get("provider"))
    if not prov:
        raise LLMError("No model provider is selected.")
    base = (cfg.get("base_url") or prov["base_url"] or "").rstrip("/")
    if not base:
        raise LLMError("This provider needs a base URL.")
    key = cfg.get("api_key") or os.environ.get("MODEL_API_KEY") or ""
    if not key and not prov.get("no_key"):
        raise LLMError("Add an API key first.")
    return base, key, (cfg.get("model") or prov["default_model"] or "")


def _request(url, key, payload=None, timeout=45):
    headers = {"Content-Type": "application/json", "Accept": "application/json",
               "User-Agent": "graph-desk/0.1"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method="POST" if payload is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return json.loads(res.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(body)
            detail = detail.get("error", detail)
            if isinstance(detail, dict):
                detail = detail.get("message") or json.dumps(detail)
        except ValueError:
            detail = body[:300]
        hint = {401: " (the key was rejected)", 403: " (the key may lack access)",
                404: " (check the base URL or model name)", 429: " (rate limited or out of credit)"}.get(err.code, "")
        raise LLMError(f"{err.code}{hint}: {str(detail)[:300]}") from err
    except urllib.error.URLError as err:
        raise LLMError(f"Could not reach the provider: {err.reason}") from err
    except TimeoutError as err:
        raise LLMError("The provider took too long to answer.") from err


def chat(cfg, messages, json_mode=False, max_tokens=1500, temperature=0):
    """Returns the assistant text."""
    base, key, model = resolve(cfg)
    if not model:
        raise LLMError("Pick a model first.")
    payload = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    url = f"{base}/chat/completions"
    for _ in range(3):
        try:
            out = _request(url, key, payload)
            break
        except LLMError as err:
            msg = str(err)
            if not msg.startswith(("400", "422")):
                raise
            # providers differ: some reject response_format, newer OpenAI models want
            # max_completion_tokens and no temperature. Adapt once per problem.
            if "response_format" in payload and ("response_format" in msg.lower() or "json" in msg.lower()):
                payload.pop("response_format")
            elif "max_completion_tokens" in msg and "max_tokens" in payload:
                payload["max_completion_tokens"] = payload.pop("max_tokens")
                payload.pop("temperature", None)
            elif "temperature" in msg.lower() and "temperature" in payload:
                payload.pop("temperature")
            else:
                raise
    else:
        raise LLMError("The provider rejected the request.")
    try:
        return out["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as err:
        raise LLMError("The provider returned an unexpected reply.") from err


def parse_json(text):
    """Pull the first JSON object out of a model reply, even inside a code fence."""
    text = (text or "").strip()
    try:
        return json.loads(text)
    except ValueError:
        pass
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise LLMError("The model did not return JSON.")
    try:
        return json.loads(m.group(0))
    except ValueError as err:
        raise LLMError("The model returned broken JSON.") from err


def list_models(cfg):
    """Model ids the key can use. Empty list when the provider has no list endpoint."""
    base, key, _ = resolve(cfg)
    out = _request(f"{base}/models", key, timeout=20)
    items = out.get("data") if isinstance(out, dict) else out
    ids = sorted({(m.get("id") or m.get("name") or "").removeprefix("models/") for m in (items or []) if isinstance(m, dict)})
    return [i for i in ids if i]


def test(cfg):
    started = time.perf_counter()
    reply = chat(cfg, [{"role": "user", "content": "Reply with the single word OK."}], max_tokens=8)
    return {"ok": True, "reply": reply.strip()[:40], "ms": round((time.perf_counter() - started) * 1000)}
