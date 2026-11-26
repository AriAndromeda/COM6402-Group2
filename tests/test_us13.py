"""US13 – LLM integration adapter (Sprint 1 attempt)."""

import logging
from unittest.mock import MagicMock, patch

import pytest

from llm_adapter import (
    LlmAdapter,
    LlmConfig,
    LlmRateLimitError,
    get_adapter,
)


SECRET_KEY = "sk-test-secret-do-not-leak-12345"


class TestLlmConfig:
    def test_defaults_to_mock_provider(self, monkeypatch):
        monkeypatch.delenv("HEATSHIELD_LLM_PROVIDER", raising=False)
        monkeypatch.delenv("HEATSHIELD_LLM_API_KEY", raising=False)
        config = LlmConfig.from_environ()
        assert config.provider == "mock"
        assert config.api_key == ""

    def test_reads_provider_and_key_from_env(self, monkeypatch):
        monkeypatch.setenv("HEATSHIELD_LLM_PROVIDER", "openai")
        monkeypatch.setenv("HEATSHIELD_LLM_API_KEY", SECRET_KEY)
        monkeypatch.setenv("HEATSHIELD_LLM_MODEL", "gpt-4o-mini")
        config = LlmConfig.from_environ()
        assert config.provider == "openai"
        assert config.api_key == SECRET_KEY
        assert config.model == "gpt-4o-mini"


class TestLlmAdapterMockMode:
    def test_mock_generate_returns_advice_without_api_key(self):
        adapter = LlmAdapter(LlmConfig(provider="mock", api_key=""))
        result = adapter.generate("Elderly resident needs cooling advice")
        assert result["provider"] == "mock"
        assert result["mode"] == "mock"
        assert "text" in result and result["text"]
        assert SECRET_KEY not in result["text"]

    def test_openai_without_key_falls_back_to_mock(self):
        adapter = LlmAdapter(LlmConfig(provider="openai", api_key=""))
        result = adapter.generate("Need heatwave tips")
        assert result["mode"] == "mock"
        assert result["provider"] == "mock"


class TestLlmCredentialSafety:
    def test_public_status_never_includes_api_key(self):
        adapter = LlmAdapter(
            LlmConfig(provider="openai", api_key=SECRET_KEY, model="gpt-4o-mini")
        )
        status = adapter.public_status()
        blob = str(status)
        assert SECRET_KEY not in blob
        assert "api_key" not in status
        assert status["configured"] is True
        assert status["provider"] == "openai"

    def test_generate_error_redacts_api_key(self):
        adapter = LlmAdapter(
            LlmConfig(provider="openai", api_key=SECRET_KEY, model="gpt-4o-mini")
        )

        def boom(*_args, **_kwargs):
            raise RuntimeError(f"upstream failed for key {SECRET_KEY}")

        with patch("llm_adapter.requests.post", side_effect=boom):
            result = adapter.generate("hello")

        blob = str(result)
        assert SECRET_KEY not in blob
        # Rate-limit / failure path should still return usable mock advice.
        assert result["mode"] == "mock"
        assert result["text"]

    def test_logs_do_not_contain_api_key(self, caplog):
        adapter = LlmAdapter(
            LlmConfig(provider="openai", api_key=SECRET_KEY, model="gpt-4o-mini")
        )

        def boom(*_args, **_kwargs):
            raise RuntimeError(f"bad key {SECRET_KEY}")

        with caplog.at_level(logging.WARNING), patch(
            "llm_adapter.requests.post", side_effect=boom
        ):
            adapter.generate("hello")

        assert SECRET_KEY not in caplog.text


class TestLlmRateLimitFallback:
    def test_rate_limit_switches_to_mock(self):
        adapter = LlmAdapter(
            LlmConfig(provider="openai", api_key=SECRET_KEY, model="gpt-4o-mini")
        )
        response = MagicMock()
        response.status_code = 429
        response.text = "rate limit exceeded"

        with patch("llm_adapter.requests.post", return_value=response):
            result = adapter.generate("cooling centre advice")

        assert result["mode"] == "mock"
        assert result.get("fallback_reason") == "rate_limit"
        assert SECRET_KEY not in str(result)


class TestLlmApiEndpoints:
    def test_llm_status_endpoint(self, client, monkeypatch):
        monkeypatch.setenv("HEATSHIELD_LLM_PROVIDER", "mock")
        monkeypatch.delenv("HEATSHIELD_LLM_API_KEY", raising=False)
        # Reset cached adapter between env changes.
        get_adapter.cache_clear()

        resp = client.get("/api/llm/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["provider"] == "mock"
        assert "api_key" not in data
        assert SECRET_KEY not in str(data)

    def test_llm_generate_endpoint_mock(self, client, monkeypatch):
        monkeypatch.setenv("HEATSHIELD_LLM_PROVIDER", "mock")
        get_adapter.cache_clear()

        resp = client.post(
            "/api/llm/generate",
            json={"prompt": "What should staff tell residents in a heatwave?"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["mode"] == "mock"
        assert data["text"]
        assert "api_key" not in data

    def test_llm_generate_requires_prompt(self, client, monkeypatch):
        monkeypatch.setenv("HEATSHIELD_LLM_PROVIDER", "mock")
        get_adapter.cache_clear()

        resp = client.post("/api/llm/generate", json={})
        assert resp.status_code == 400
        assert "error" in resp.get_json()
        assert SECRET_KEY not in str(resp.get_json())

    def test_llm_generate_response_redacts_secret_on_failure(
        self, client, monkeypatch
    ):
        monkeypatch.setenv("HEATSHIELD_LLM_PROVIDER", "openai")
        monkeypatch.setenv("HEATSHIELD_LLM_API_KEY", SECRET_KEY)
        get_adapter.cache_clear()

        response = MagicMock()
        response.status_code = 429
        response.text = f"limited key={SECRET_KEY}"

        with patch("llm_adapter.requests.post", return_value=response):
            resp = client.post(
                "/api/llm/generate",
                json={"prompt": "advice please"},
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["mode"] == "mock"
        assert SECRET_KEY not in str(data)
        assert SECRET_KEY not in str(resp.data)


def test_rate_limit_error_message_is_safe():
    err = LlmRateLimitError(f"429 for {SECRET_KEY}")
    assert SECRET_KEY not in err.safe_message(SECRET_KEY)
