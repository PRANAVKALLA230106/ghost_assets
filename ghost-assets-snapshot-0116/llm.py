"""Role B, step 2. The ONLY place that talks to the LLM provider.

Every call is cached on disk in backend/cache/<sha256>.json keyed by
(base_url, model, system, input, image bytes, tool schemas). A cache hit makes no network call.
Provider settings come from .env: OPENAI_BASE_URL, OPENAI_API_KEY, LLM_MODEL
(we use Groq's OpenAI-compatible endpoint). AGENT_MODEL optionally overrides the model for tool calls.
Calls that include images go to a separate OpenAI-compatible endpoint when VISION_BASE_URL is set
(VISION_API_KEY, VISION_MODEL; e.g. Gemini), and are cached under that base URL. LLM_CACHE_ONLY=1 serves from the cache only and
raises CacheMiss instead of calling the provider (offline re-runs, demo safety).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any

import openai
from dotenv import load_dotenv
from openai import OpenAI

CACHE_DIR = Path(__file__).parent / "cache"
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

MAX_RETRIES = 3                 # retries after the first attempt (bad JSON, transient errors)
MAX_RATE_LIMIT_WAITS = 30       # separate budget for per-minute 429s (each sleeps retry-after)
MAX_RETRY_AFTER = 60.0          # cap on a provider-supplied retry-after, in seconds
IMAGE_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}

_clients: dict[str, OpenAI] = {}
_stats = {"hits": 0, "misses": 0}
_lock = threading.Lock()


class RetryableError(Exception):
    """A failed attempt worth repeating: bad JSON or a malformed tool call."""


class OutputTruncated(Exception):
    """The reply hit max_tokens. Repeating the same request will not help; the caller should send less."""


class CacheMiss(Exception):
    """LLM_CACHE_ONLY=1 and the request is not cached: no network call is made."""


def _cache_only() -> bool:
    return os.getenv("LLM_CACHE_ONLY") == "1"


def _endpoint(vision: bool = False) -> tuple[str | None, str | None]:
    """(base_url, api_key): the VISION_* endpoint for image calls when configured, else OPENAI_*."""
    if vision and os.getenv("VISION_BASE_URL"):
        return os.getenv("VISION_BASE_URL"), os.getenv("VISION_API_KEY")
    return os.getenv("OPENAI_BASE_URL"), os.getenv("OPENAI_API_KEY")


def _get_client(vision: bool = False) -> OpenAI:
    base_url, api_key = _endpoint(vision)
    if base_url not in _clients:
        # max_retries=0: retries are handled here so they are logged and honour retry-after.
        _clients[base_url] = OpenAI(base_url=base_url, api_key=api_key, max_retries=0)
    return _clients[base_url]


def _json_model() -> str:
    model = os.getenv("LLM_MODEL")
    if not model:
        raise RuntimeError("LLM_MODEL is not set in .env")
    return model


def _tools_model() -> str:
    return os.getenv("AGENT_MODEL") or _json_model()


def _vision_model() -> str:
    return os.getenv("VISION_MODEL") or _json_model()


def _reasoning_args(model: str) -> dict[str, str]:
    """REASONING_EFFORT (low|medium|high) for reasoning models; hidden reasoning tokens count
    against the free tier's daily token quota, so 'low' stretches it."""
    effort = os.getenv("REASONING_EFFORT")
    return {"reasoning_effort": effort} if effort and model.startswith("openai/gpt-oss") else {}


# ---- cache -------------------------------------------------------------------------------------

def _cache_key(payload: dict[str, Any], vision: bool = False) -> str:
    blob = json.dumps({"base_url": _endpoint(vision)[0], **payload}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _cache_get(key: str) -> Any | None:
    path = CACHE_DIR / f"{key}.json"
    if not path.exists():
        with _lock:
            _stats["misses"] += 1
        return None
    with _lock:
        _stats["hits"] += 1
    return json.loads(path.read_text(encoding="utf-8"))


def _cache_put(key: str, value: Any) -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    tmp = CACHE_DIR / f"{key}.{threading.get_ident()}.tmp"
    tmp.write_text(json.dumps(value, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(CACHE_DIR / f"{key}.json")


def cache_stats() -> dict[str, int]:
    """{"hits": n, "misses": n} for this process - print it after runs to prove caching works."""
    with _lock:
        return dict(_stats)


# ---- retries -----------------------------------------------------------------------------------

def _retry_delay(exc: Exception, attempt: int) -> float:
    if isinstance(exc, openai.RateLimitError):
        header = exc.response.headers.get("retry-after")
        try:
            return min(float(header), MAX_RETRY_AFTER)
        except (TypeError, ValueError):
            pass
    return 2.0 ** (attempt + 1)          # 2s, 4s, 8s


def _is_rate_limit(exc: Exception) -> bool:
    """A 429 worth waiting out. Not: "Request too large" (per-request limit) or a per-day quota."""
    if not isinstance(exc, openai.RateLimitError):
        return False
    msg = str(exc)
    return "Request too large" not in msg and "per day" not in msg


def _limit_kind(exc: Exception) -> str:
    m = re.search(r"on (\w+ per \w+) \((\w+)\)", str(exc))
    return f"{m.group(1)} ({m.group(2)})" if m else "unknown limit"


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, (RetryableError, openai.APIConnectionError, openai.InternalServerError)):
        return True
    # Groq answers 400 "tool_use_failed" / "json_validate_failed" when the model emits malformed output.
    return isinstance(exc, openai.BadRequestError) and any(
        code in str(exc) for code in ("tool_use_failed", "json_validate_failed"))


def _with_retries(label: str, fn):
    """MAX_RETRIES for bad output / transient errors; rate limits get their own, larger budget
    because concurrent batches on a free tier hit the per-minute token limit routinely."""
    errors = waits = 0
    while True:
        try:
            return fn()
        except Exception as exc:
            if _is_rate_limit(exc) and waits < MAX_RATE_LIMIT_WAITS:
                waits += 1
                delay = _retry_delay(exc, waits - 1)
                print(f"[llm] {label}: 429 on {_limit_kind(exc)}; sleeping {delay:.1f}s (wait {waits}/{MAX_RATE_LIMIT_WAITS})")
            elif _is_retryable(exc) and errors < MAX_RETRIES:
                errors += 1
                delay = _retry_delay(exc, errors - 1)
                print(f"[llm] {label}: {type(exc).__name__} ({str(exc)[:120]}); retry {errors}/{MAX_RETRIES} in {delay:.1f}s")
            else:
                raise
            time.sleep(delay)


# ---- public API --------------------------------------------------------------------------------

def _image_part(path: Path) -> dict:
    mime = IMAGE_MIME.get(path.suffix.lower(), "image/png")
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}}


def call_llm_json(system: str, user: str, images: list[Path] | None = None,
                  max_tokens: int | None = None, meta: dict | None = None) -> dict[str, Any]:
    """Ask for a JSON object and return it parsed. Retries 3x on invalid JSON, waits out rate limits.
    Raises OutputTruncated if the reply hit max_tokens (finish_reason == "length").
    meta, if given, is filled with {"cache": "hit"|"miss", "finish_reason": ...}."""
    meta = meta if meta is not None else {}
    images = [Path(p) for p in images or []]
    model = _vision_model() if images else _json_model()
    payload = {
        "kind": "json", "model": model, "system": system, "user": user,
        "images": [hashlib.sha256(p.read_bytes()).hexdigest() for p in images],
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    reasoning = _reasoning_args(model)
    payload.update(reasoning)
    key = _cache_key(payload, vision=bool(images))
    cached = _cache_get(key)
    if cached is not None:
        meta.update(cache="hit", finish_reason="cached")
        return cached
    meta["cache"] = "miss"
    if _cache_only():
        raise CacheMiss(f"json call not cached (key {key[:12]})")

    content: str | list[dict] = user
    if images:
        content = [{"type": "text", "text": user}] + [_image_part(p) for p in images]
    messages = [{"role": "system", "content": system}, {"role": "user", "content": content}]
    extra = {"max_tokens": max_tokens} if max_tokens is not None else {}
    if reasoning:
        extra["extra_body"] = reasoning

    def attempt() -> dict[str, Any]:
        resp = _get_client(vision=bool(images)).chat.completions.create(
            model=model, messages=messages, response_format={"type": "json_object"}, temperature=0, **extra,
        )
        choice = resp.choices[0]
        meta["finish_reason"] = choice.finish_reason
        if choice.finish_reason == "length":
            raise OutputTruncated(f"reply hit max_tokens={max_tokens} (finish_reason=length)")
        text = choice.message.content or ""
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RetryableError(f"invalid JSON: {exc}; got {text[:80]!r}") from exc
        if not isinstance(parsed, dict):
            raise RetryableError(f"expected a JSON object, got {type(parsed).__name__}")
        return parsed

    result = _with_retries("json", attempt)
    _cache_put(key, result)
    return result


def _failed_generation(exc: Exception) -> str:
    """Text the provider rejected for having no tool call (Groq's 'failed_generation'), if any."""
    body = getattr(exc, "body", None)
    err = body.get("error", body) if isinstance(body, dict) else None
    return str(err.get("failed_generation") or "").strip() if isinstance(err, dict) else ""


def call_llm_tools(system: str, messages: list[dict], tools: list[dict]) -> dict[str, Any]:
    """One tool-calling turn. Returns {"text": str, "reasoning": str, "tool_call": {"id", "name", "args"} | None,
    "raw": <provider message to append to history>}. tool_choice is "required": every turn calls a tool
    (the loop ends with finish()). "reasoning" is the model's separate reasoning field (gpt-oss), if any."""
    model = _tools_model()
    reasoning_args = _reasoning_args(model)
    key = _cache_key({"kind": "tools", "model": model, "system": system, "messages": messages, "tools": tools,
                      "tool_choice": "required", **reasoning_args})
    cached = _cache_get(key)
    if cached is not None:
        return cached
    if _cache_only():
        raise CacheMiss(f"tools call not cached (key {key[:12]})")

    full = [{"role": "system", "content": system}, *messages]

    def attempt() -> dict[str, Any]:
        try:
            resp = _get_client().chat.completions.create(
                model=model, messages=full, tools=tools, tool_choice="required", parallel_tool_calls=False,
                temperature=0, **({"extra_body": reasoning_args} if reasoning_args else {}),
            )
        except openai.BadRequestError as exc:
            # The model answered in prose despite tool_choice=required. Retrying the same request at
            # temperature 0 gives the same prose, so hand it back as a turn with no tool call.
            text = _failed_generation(exc)
            if "did not call a tool" not in str(exc) or not text:
                raise
            return {"text": text, "reasoning": "", "tool_call": None, "raw": {"role": "assistant", "content": text}}
        msg = resp.choices[0].message
        text = msg.content or ""
        reasoning = str((msg.model_extra or {}).get("reasoning") or "")
        raw: dict[str, Any] = {"role": "assistant", "content": text}
        tool_call = None
        if msg.tool_calls:
            tc = msg.tool_calls[0]   # one call per turn; any extras are dropped so history stays consistent
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError as exc:
                raise RetryableError(f"invalid tool arguments for {tc.function.name}: {exc}") from exc
            tool_call = {"id": tc.id, "name": tc.function.name, "args": args}
            raw["tool_calls"] = [{"id": tc.id, "type": "function",
                                  "function": {"name": tc.function.name, "arguments": tc.function.arguments or "{}"}}]
        return {"text": text, "reasoning": reasoning, "tool_call": tool_call, "raw": raw}

    try:
        result = _with_retries("tools", attempt)
    except openai.BadRequestError as exc:
        # Still malformed after retries (e.g. gpt-oss naming a tool 'finish<|channel|>commentary'):
        # return a turn with no tool call so the agent loop can nudge the model instead of crashing.
        if "tool_use_failed" not in str(exc):
            raise
        print(f"[llm] tools: malformed tool call after retries; returning it as a turn with no tool call")
        text = _failed_generation(exc)
        result = {"text": text, "reasoning": "", "tool_call": None, "raw": {"role": "assistant", "content": text}}
    _cache_put(key, result)
    return result
