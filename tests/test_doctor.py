import httpx
import pytest

from counterwrench.config import resolve_models
from counterwrench.doctor import (
    CheckResult,
    describe_env,
    fix_hint,
    langsmith_status,
    normalize_provider,
    unique_models,
    verify_pinning,
)

PINNED = {"OPENROUTER_API_KEY": "sk-or-secret", "OPENROUTER_PROVIDER_ORDER": "anthropic,openai"}


def test_shared_model_is_checked_once():
    config = resolve_models(PINNED)
    assert unique_models(config) == {
        "openrouter:anthropic/claude-haiku-5.5": ["agent", "triage"],
        "openrouter:openai/gpt-6.1-sol": ["judge"],
    }


def test_describe_env_never_prints_values():
    env = {"OPENROUTER_API_KEY": "sk-or-secret", "ANTHROPIC_BASE_URL": "http://127.0.0.1:8787"}
    output = "\n".join(describe_env(env))
    assert "sk-or-secret" not in output
    assert "127.0.0.1" not in output
    assert "ANTHROPIC_BASE_URL" in output


def test_base_url_override_only_reported_when_set():
    assert not any("BASE_URL" in line for line in describe_env({"OPENROUTER_API_KEY": "x"}))


@pytest.mark.parametrize(
    ("env", "ok"),
    [
        ({"LANGSMITH_TRACING": "true"}, False),
        ({"LANGSMITH_TRACING": "true", "LANGSMITH_API_KEY": "lsv2"}, True),
        ({"LANGSMITH_TRACING": "false"}, True),
        ({}, True),
    ],
)
def test_tracing_on_without_key_fails(env, ok):
    assert langsmith_status(env)[1] is ok


def _http_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://example.test")
    response = httpx.Response(status, request=request)
    return httpx.HTTPStatusError(f"Error code: {status}", request=request, response=response)


class StatusError(Exception):
    def __init__(self, status_code: int):
        super().__init__("provider error")
        self.status_code = status_code


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (StatusError(401), "OPENROUTER_API_KEY"),
        (StatusError(402), "credits"),
        (StatusError(404), "Model not found"),
        (_http_error(429), "Rate limited"),
        (ValueError("this endpoint does not support response_format"), "structured output"),
        (ValueError("something odd"), "Unexpected error: ValueError"),
    ],
)
def test_fix_hint_matches_error(exc, expected):
    assert expected in fix_hint(exc, "openrouter:anthropic/claude-haiku-5.5")


def test_normalize_provider_matches_order_slugs():
    assert normalize_provider("Amazon Bedrock") == "amazon-bedrock"
    assert normalize_provider("OpenAI") == "openai"


def _result(served_by: str | None) -> CheckResult:
    return CheckResult(
        "openrouter:anthropic/claude-haiku-5.5", "tool calling", True, 0.5, "ok", "gen-1", served_by
    )


def test_pinning_passes_when_served_in_order():
    result = _result("Anthropic")
    verify_pinning([result], resolve_models(PINNED))
    assert result.ok


def test_pinning_fails_when_served_outside_order():
    result = _result("Amazon Bedrock")
    verify_pinning([result], resolve_models(PINNED))
    assert not result.ok
    assert "outside OPENROUTER_PROVIDER_ORDER" in result.detail


def test_pinning_fails_when_backend_unknown():
    result = _result(None)
    verify_pinning([result], resolve_models(PINNED))
    assert not result.ok
