"""
Thin wrapper around your own Claude (Anthropic Messages API) endpoint.

Everything is driven by environment variables so you can point it at your own
gateway / proxy without code changes:

  ANTHROPIC_API_KEY    your key           (required to enable AI features)
  ANTHROPIC_BASE_URL   endpoint base URL  (default https://api.anthropic.com)
  ANTHROPIC_MODEL      model id           (default claude-sonnet-4-5)
  ANTHROPIC_VERSION    API version header (default 2023-06-01)

If no key is set, `is_configured` is False and every call is a safe no-op —
the app still works end-to-end on the deterministic statistical path.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Optional

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")


class ClaudeClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        version: Optional[str] = None,
        timeout: float = 60.0,
    ):
        self.api_key = api_key if api_key is not None else os.getenv("ANTHROPIC_API_KEY", "")
        self.base_url = (base_url or os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")).rstrip("/")
        self.model = model or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
        self.version = version or os.getenv("ANTHROPIC_VERSION", "2023-06-01")
        self.timeout = timeout

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def complete_text(self, prompt: str, max_tokens: int = 1024,
                      system: Optional[str] = None) -> Optional[str]:
        if not self.is_configured:
            return None
        url = f"{self.base_url}/v1/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": self.version,
            "content-type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            payload["system"] = system
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(url, headers=headers, json=payload)
                if resp.status_code >= 400:
                    try:
                        detail = resp.json()
                    except ValueError:
                        detail = resp.text
                    raise RuntimeError(f"Anthropic API error {resp.status_code}: {detail}")
                data = resp.json()
            parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
            return "\n".join(p for p in parts if p).strip() or None
        except Exception as exc:  # network / auth / rate-limit: degrade gracefully
            print(f"[claude] request failed for model={self.model} url={url}: {exc}")
            return None

    def complete_json(self, prompt: str, max_tokens: int = 1024) -> Optional[Any]:
        """Ask for JSON and parse it, tolerating stray prose or code fences."""
        text = self.complete_text(
            prompt,
            max_tokens=max_tokens,
            system="You return only valid JSON. No commentary, no markdown fences.",
        )
        if not text:
            return None
        return _extract_json(text)


def _extract_json(text: str) -> Optional[Any]:
    text = text.strip()
    # strip ```json ... ``` fences if present
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # last resort: grab the first {...} or [...] block
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                continue
    return None
