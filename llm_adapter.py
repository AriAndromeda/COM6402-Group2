"""US13 – Configurable LLM integration adapter (Sprint 1 attempt).

Supports a mock provider by default and an optional OpenAI-compatible
HTTP provider configured via environment variables. Credentials stay in
process memory / env only and are never returned in API payloads or logs.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import requests

logger = logging.getLogger(__name__)

ALLOWED_PROVIDERS = ("mock", "openai")
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"

MOCK_ADVICE = (
    "Heat Shield mock advice: stay hydrated, keep indoor spaces cool, "
    "check on vulnerable neighbours, and use a cooling centre if your "
    "home is unsafe in the heat. This response was generated locally "
    "without calling an external AI service."
)


class LlmRateLimitError(Exception):
    """Raised when an upstream LLM provider returns HTTP 429."""

    def safe_message(self, api_key: str = "") -> str:
        return _redact(str(self), api_key) or "LLM rate limit exceeded"


@dataclass(frozen=True)
class LlmConfig:
    provider: str = "mock"
    api_key: str = ""
    model: str = DEFAULT_MODEL
    base_url: str = DEFAULT_OPENAI_BASE_URL

    @classmethod
    def from_environ(cls) -> "LlmConfig":
        provider = os.environ.get("HEATSHIELD_LLM_PROVIDER", "mock").strip().lower()
        if provider not in ALLOWED_PROVIDERS:
            provider = "mock"
        return cls(
            provider=provider,
            api_key=os.environ.get("HEATSHIELD_LLM_API_KEY", "").strip(),
            model=os.environ.get("HEATSHIELD_LLM_MODEL", DEFAULT_MODEL).strip()
            or DEFAULT_MODEL,
            base_url=os.environ.get(
                "HEATSHIELD_LLM_BASE_URL", DEFAULT_OPENAI_BASE_URL
            ).strip()
            or DEFAULT_OPENAI_BASE_URL,
        )


def _redact(text: str, api_key: str) -> str:
    if not text:
        return text
    redacted = text
    if api_key:
        redacted = redacted.replace(api_key, "[REDACTED]")
    return redacted


class LlmAdapter:
    """Small adapter around mock / OpenAI-compatible completion APIs."""

    def __init__(self, config: LlmConfig | None = None):
        self.config = config or LlmConfig.from_environ()

    def public_status(self) -> dict[str, Any]:
        """Safe status payload — never includes credentials."""
        configured = bool(self.config.api_key) if self.config.provider != "mock" else True
        return {
            "provider": self.config.provider,
            "model": self.config.model if self.config.provider != "mock" else "mock",
            "configured": configured,
            "mode": "mock" if self.config.provider == "mock" or not self.config.api_key else "live",
        }

    def generate(self, prompt: str) -> dict[str, Any]:
        """Return generated text. Falls back to mock on missing key / errors / 429."""
        cleaned = (prompt or "").strip()
        if not cleaned:
            raise ValueError("prompt is required")

        if self.config.provider == "mock" or not self.config.api_key:
            return self._mock_result(cleaned)

        try:
            return self._generate_openai(cleaned)
        except LlmRateLimitError as exc:
            logger.warning(
                "LLM rate limit; switching to mock mode (%s)",
                exc.safe_message(self.config.api_key),
            )
            result = self._mock_result(cleaned)
            result["fallback_reason"] = "rate_limit"
            return result
        except Exception as exc:  # noqa: BLE001 - adapter must never leak upstream detail
            logger.warning(
                "LLM provider error; switching to mock mode (%s)",
                _redact(str(exc), self.config.api_key),
            )
            result = self._mock_result(cleaned)
            result["fallback_reason"] = "provider_error"
            return result

    def _mock_result(self, prompt: str) -> dict[str, Any]:
        return {
            "provider": "mock",
            "mode": "mock",
            "model": "mock",
            "text": MOCK_ADVICE,
            "prompt_echo": prompt[:200],
        }

    def _generate_openai(self, prompt: str) -> dict[str, Any]:
        url = f"{self.config.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.config.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are Heat Shield, a heatwave support assistant. "
                        "Give concise, practical safety advice for staff helping the public."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
        }

        response = requests.post(url, headers=headers, json=payload, timeout=20)
        if response.status_code == 429:
            raise LlmRateLimitError("LLM provider returned HTTP 429")
        if response.status_code >= 400:
            # Do not include response body — it may echo credentials.
            raise RuntimeError(f"LLM provider returned HTTP {response.status_code}")

        data = response.json()
        text = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
        if not text:
            raise RuntimeError("LLM provider returned an empty completion")

        return {
            "provider": "openai",
            "mode": "live",
            "model": self.config.model,
            "text": text,
        }


@lru_cache(maxsize=1)
def get_adapter() -> LlmAdapter:
    """Cached adapter built from the current process environment."""
    return LlmAdapter(LlmConfig.from_environ())
