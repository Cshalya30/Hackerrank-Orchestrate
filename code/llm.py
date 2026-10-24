"""Thin wrapper around the Gemini Flash API: disk cache, retries, token ledger.

Used only by intent.py (request classification) and ingest/image_parser.py
(screenshot evidence). Every other module is deterministic. All prompt
inputs drawn from dataset/ are untrusted data, never instructions.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from config import GEMINI_API_KEY, GEMINI_MODEL, LLM_CACHE_DIR, LLM_LEDGER_JSONL

LLM_CACHE_DIR.mkdir(parents=True, exist_ok=True)


class LLMUnavailable(RuntimeError):
    """Raised when no API key is configured. Callers must have a deterministic fallback."""


def _cache_key(model: str, prompt: str) -> str:
    return hashlib.sha256(f"{model}\n{prompt}".encode("utf-8")).hexdigest()


def _cache_path(key: str) -> Path:
    return LLM_CACHE_DIR / f"{key}.json"


def _append_ledger(entry: dict[str, Any]) -> None:
    with open(LLM_LEDGER_JSONL, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def is_configured() -> bool:
    return bool(GEMINI_API_KEY)


def call(prompt: str, *, system: str | None = None, image_bytes: bytes | None = None,
          model: str = GEMINI_MODEL, max_retries: int = 3) -> str:
    """Call the model with disk caching and a token ledger. Returns raw text response.

    Cache key covers model + prompt text only (image calls are cached by the
    caller passing a stable text description of the image alongside the bytes
    hash, since binary content cannot be part of a readable cache key).
    """
    if not is_configured():
        raise LLMUnavailable("GEMINI_API_KEY not set; caller must use its deterministic fallback")

    key = _cache_key(model, (system or "") + "\n" + prompt + (hashlib.sha256(image_bytes).hexdigest() if image_bytes else ""))
    cached = _cache_path(key)
    if cached.exists():
        data = json.loads(cached.read_text(encoding="utf-8"))
        _append_ledger({"model": model, "cached": True, "input_tokens": 0, "output_tokens": 0, "key": key})
        return data["text"]

    import google.generativeai as genai  # local import: optional dependency

    genai.configure(api_key=GEMINI_API_KEY)
    gm = genai.GenerativeModel(model_name=model, system_instruction=system or None)

    parts: list[Any] = [prompt]
    if image_bytes is not None:
        parts.append({"mime_type": "image/png", "data": image_bytes})

    last_err: Exception | None = None
    for attempt in range(max_retries):
        try:
            resp = gm.generate_content(parts)
            text = resp.text
            usage = getattr(resp, "usage_metadata", None)
            input_tokens = getattr(usage, "prompt_token_count", 0) if usage else 0
            output_tokens = getattr(usage, "candidates_token_count", 0) if usage else 0
            cached.write_text(json.dumps({"text": text}, ensure_ascii=False), encoding="utf-8")
            _append_ledger({
                "model": model, "cached": False,
                "input_tokens": input_tokens, "output_tokens": output_tokens,
                "key": key,
            })
            return text
        except Exception as exc:  # noqa: BLE001 - broad: retry any transient API error
            last_err = exc
            time.sleep(1.5 * (attempt + 1))

    raise RuntimeError(f"LLM call failed after {max_retries} attempts: {last_err}")
