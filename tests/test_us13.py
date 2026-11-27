"""US13 – LLM integration adapter (Sprint 1 attempt)."""

import logging
from unittest.mock import MagicMock, patch

import pytest
import requests

from llm_adapter import (
    FALLBACK_PREFIX,
    MAX_PROMPT_LENGTH,
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
        monkeypatch.delenv("HEATSHIELD_LLM_ALLOW_EXTERNAL", raising=False)
        config = LlmConfig.from_environ()
        assert config.provider == "mock"
        assert config.api_key == ""
        assert config.allow_external is False

    def test_reads_provider_and_key_from_env(self, monkeypatch):
        monkeypatch.setenv("HEATSHIELD_LLM_PROVIDER", "openai")
        monkeypatch.setenv("HEATSHIELD_LLM_API_KEY", SECRET_KEY)
        monkeypatch.setenv("HEATSHIELD_LLM_MODEL", "gpt-4o-mini")
        monkeypatch.setenv("HEATSHIELD_LLM_ALLOW_EXTERNAL", "true")
        config = LlmConfig.from_environ()
        assert config.provider == "openai"
        assert config.api_key == SECRET_KEY
        assert config.model == "gpt-4o-mini"
        assert config.allow_external is True


class TestLlmAdapterMockMode:
    def test_mock_generate_returns_advice_without_api_key(self):
        adapter = LlmAdapter(LlmConfig(provider="mock", api_key=""))
        result = adapter.generate("Elderly resident needs cooling advice")
        assert result["provider"] == "mock"
        assert result["mode"] == "mock"
        assert result["simulated"] is True
        assert result["is_live"] is False
        assert "text" in result and result["text"]
        assert SECRET_KEY not in result["text"]

    def test_openai_without_key_falls_back_to_mock(self):
        adapter = LlmAdapter(LlmConfig(provider="openai", api_key=""))
        result = adapter.generate("Need heatwave tips")
        assert result["mode"] == "mock"
        assert result["provider"] == "mock"
        assert result["simulated"] is True

    def test_live_disabled_without_allow_external_flag(self):
        adapter = LlmAdapter(
            LlmConfig(
                provider="openai",
                api_key=SECRET_KEY,
                allow_external=False,
            )
        )
        result = adapter.generate("fictional heatwave case")
        assert result["mode"] == "mock"
        assert result["fallback_reason"] == "external_calls_disabled"
        assert result["text"].startswith(FALLBACK_PREFIX)
        assert result["simulated"] is True


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
        assert "privacy_note" in status

    def test_generate_error_redacts_api_key(self):
        adapter = LlmAdapter(
            LlmConfig(
                provider="openai",
                api_key=SECRET_KEY,
                model="gpt-4o-mini",
                allow_external=True,
            )
        )

        def boom(*_args, **_kwargs):
            raise RuntimeError(f"upstream failed for key {SECRET_KEY}")

        with patch("llm_adapter.requests.post", side_effect=boom):
            result = adapter.generate("hello")

        blob = str(result)
        assert SECRET_KEY not in blob
        assert result["mode"] == "mock"
        assert result["fallback_reason"] == "provider_error"
        assert result["text"].startswith(FALLBACK_PREFIX)

    def test_logs_do_not_contain_api_key(self, caplog):
        adapter = LlmAdapter(
            LlmConfig(
                provider="openai",
                api_key=SECRET_KEY,
                model="gpt-4o-mini",
                allow_external=True,
            )
        )

        def boom(*_args, **_kwargs):
            raise RuntimeError(f"bad key {SECRET_KEY}")

        with caplog.at_level(logging.WARNING), patch(
            "llm_adapter.requests.post", side_effect=boom
        ):
            adapter.generate("hello")

        assert SECRET_KEY not in caplog.text


class TestLlmRateLimitAndErrors:
    def test_rate_limit_switches_to_mock_with_transparent_label(self):
        adapter = LlmAdapter(
            LlmConfig(
                provider="openai",
                api_key=SECRET_KEY,
                model="gpt-4o-mini",
                allow_external=True,
            )
        )
        response = MagicMock()
        response.status_code = 429
        response.text = "rate limit exceeded"

        with patch("llm_adapter.requests.post", return_value=response):
            result = adapter.generate("cooling centre advice")

        assert result["mode"] == "mock"
        assert result["fallback_reason"] == "rate_limit"
        assert result["text"].startswith(FALLBACK_PREFIX)
        assert result["simulated"] is True
        assert SECRET_KEY not in str(result)

    def test_timeout_falls_back_to_mock(self):
        adapter = LlmAdapter(
            LlmConfig(
                provider="openai",
                api_key=SECRET_KEY,
                allow_external=True,
            )
        )
        with patch(
            "llm_adapter.requests.post",
            side_effect=requests.Timeout("timed out"),
        ):
            result = adapter.generate("advice")

        assert result["fallback_reason"] == "timeout"
        assert result["text"].startswith(FALLBACK_PREFIX)

    def test_malformed_json_falls_back_to_mock(self):
        adapter = LlmAdapter(
            LlmConfig(
                provider="openai",
                api_key=SECRET_KEY,
                allow_external=True,
            )
        )
        response = MagicMock()
        response.status_code = 200
        response.json.side_effect = ValueError("not json")

        with patch("llm_adapter.requests.post", return_value=response):
            result = adapter.generate("advice")

        assert result["fallback_reason"] == "provider_error"
        assert result["simulated"] is True

    def test_successful_live_provider_with_mocked_http(self):
        adapter = LlmAdapter(
            LlmConfig(
                provider="openai",
                api_key=SECRET_KEY,
                model="gpt-4o-mini",
                allow_external=True,
            )
        )
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "choices": [
                {"message": {"content": "Live fictional heatwave advice."}}
            ]
        }

        with patch("llm_adapter.requests.post", return_value=response) as mock_post:
            result = adapter.generate("fictional case for Bolton cooling centre")

        assert result["mode"] == "live"
        assert result["is_live"] is True
        assert result["simulated"] is False
        assert result["text"] == "Live fictional heatwave advice."
        assert SECRET_KEY not in str(result)
        assert mock_post.called


class TestLlmPromptValidation:
    def test_empty_prompt_raises(self):
        adapter = LlmAdapter(LlmConfig(provider="mock"))
        with pytest.raises(ValueError, match="prompt is required"):
            adapter.generate("   ")

    def test_oversized_prompt_raises(self):
        adapter = LlmAdapter(LlmConfig(provider="mock"))
        with pytest.raises(ValueError, match="characters or fewer"):
            adapter.generate("x" * (MAX_PROMPT_LENGTH + 1))

    def test_boundary_prompt_length_accepted(self):
        adapter = LlmAdapter(LlmConfig(provider="mock"))
        result = adapter.generate("x" * MAX_PROMPT_LENGTH)
        assert result["mode"] == "mock"


class TestLlmApiEndpoints:
    def test_llm_status_endpoint(self, client, monkeypatch):
        monkeypatch.setenv("HEATSHIELD_LLM_PROVIDER", "mock")
        monkeypatch.delenv("HEATSHIELD_LLM_API_KEY", raising=False)
        get_adapter.cache_clear()

        resp = client.get("/api/llm/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["provider"] == "mock"
        assert "api_key" not in data
        assert "privacy_note" in data
        assert SECRET_KEY not in str(data)

    def test_llm_generate_requires_auth(self, client, monkeypatch):
        monkeypatch.setenv("HEATSHIELD_LLM_PROVIDER", "mock")
        get_adapter.cache_clear()

        resp = client.post(
            "/api/llm/generate",
            json={"prompt": "What should staff tell residents in a heatwave?"},
        )
        assert resp.status_code == 401
        assert "error" in resp.get_json()

    def test_llm_generate_endpoint_mock(self, client, staff_headers, monkeypatch):
        monkeypatch.setenv("HEATSHIELD_LLM_PROVIDER", "mock")
        get_adapter.cache_clear()

        resp = client.post(
            "/api/llm/generate",
            json={"prompt": "What should staff tell residents in a heatwave?"},
            headers=staff_headers,
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["mode"] == "mock"
        assert data["simulated"] is True
        assert data["text"]
        assert "api_key" not in data

    def test_llm_generate_requires_prompt(self, client, staff_headers, monkeypatch):
        monkeypatch.setenv("HEATSHIELD_LLM_PROVIDER", "mock")
        get_adapter.cache_clear()

        resp = client.post("/api/llm/generate", json={}, headers=staff_headers)
        assert resp.status_code == 400
        assert "error" in resp.get_json()

    def test_llm_generate_rejects_oversized_prompt(
        self, client, staff_headers, monkeypatch
    ):
        monkeypatch.setenv("HEATSHIELD_LLM_PROVIDER", "mock")
        get_adapter.cache_clear()

        resp = client.post(
            "/api/llm/generate",
            json={"prompt": "y" * (MAX_PROMPT_LENGTH + 1)},
            headers=staff_headers,
        )
        assert resp.status_code == 400
        assert "prompt must be" in resp.get_json()["error"]

    def test_llm_generate_accepts_boundary_prompt(
        self, client, staff_headers, monkeypatch
    ):
        monkeypatch.setenv("HEATSHIELD_LLM_PROVIDER", "mock")
        get_adapter.cache_clear()

        resp = client.post(
            "/api/llm/generate",
            json={"prompt": "z" * MAX_PROMPT_LENGTH},
            headers=staff_headers,
        )
        assert resp.status_code == 200

    def test_llm_generate_response_redacts_secret_on_failure(
        self, client, staff_headers, monkeypatch
    ):
        monkeypatch.setenv("HEATSHIELD_LLM_PROVIDER", "openai")
        monkeypatch.setenv("HEATSHIELD_LLM_API_KEY", SECRET_KEY)
        monkeypatch.setenv("HEATSHIELD_LLM_ALLOW_EXTERNAL", "true")
        get_adapter.cache_clear()

        response = MagicMock()
        response.status_code = 429
        response.text = f"limited key={SECRET_KEY}"

        with patch("llm_adapter.requests.post", return_value=response):
            resp = client.post(
                "/api/llm/generate",
                json={"prompt": "advice please"},
                headers=staff_headers,
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["mode"] == "mock"
        assert data["fallback_reason"] == "rate_limit"
        assert data["text"].startswith(FALLBACK_PREFIX)
        assert SECRET_KEY not in str(data)
        assert SECRET_KEY not in str(resp.data)


def test_rate_limit_error_message_is_safe():
    err = LlmRateLimitError(f"429 for {SECRET_KEY}")
    assert SECRET_KEY not in err.safe_message(SECRET_KEY)
