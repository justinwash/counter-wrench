import pytest

from counterwrench.config import (
    ConfigError,
    build_chat_model,
    model_family,
    resolve_models,
)

ANTHROPIC = {"ANTHROPIC_API_KEY": "sk-test"}
OPENAI = {"OPENAI_API_KEY": "sk-test"}
GOOGLE = {"GOOGLE_API_KEY": "test"}
OPENROUTER = {"OPENROUTER_API_KEY": "sk-or-test"}


def env(*parts: dict, **overrides: str) -> dict[str, str]:
    merged: dict[str, str] = {}
    for part in parts:
        merged.update(part)
    merged.update(overrides)
    return merged


def test_no_keys_is_a_clear_error():
    with pytest.raises(ConfigError, match="No LLM provider key"):
        resolve_models({})


def test_blank_key_counts_as_missing():
    with pytest.raises(ConfigError):
        resolve_models({"ANTHROPIC_API_KEY": "  "})


def test_anthropic_only_uses_same_family_judge_with_warning():
    config = resolve_models(ANTHROPIC)
    assert config.agent == "anthropic:claude-haiku-5-5"
    assert config.triage == "anthropic:claude-haiku-5-5"
    assert config.judge == "anthropic:claude-sonnet-5-5"
    assert any("self-preference" in w for w in config.warnings)


def test_two_providers_gives_cross_family_judge():
    config = resolve_models(env(ANTHROPIC, OPENAI))
    assert config.agent == "anthropic:claude-haiku-5-5"
    assert config.judge == "openai:gpt-6.1-sol"
    assert config.warnings == ()


def test_priority_order_picks_agent_provider():
    config = resolve_models(env(OPENROUTER, GOOGLE))
    assert config.agent == "google_genai:gemini-3.5-flash-lite"
    assert config.judge == "openrouter:openai/gpt-6.1-sol"


def test_openrouter_alone_still_gets_cross_family_judge():
    config = resolve_models(env(OPENROUTER, OPENROUTER_PROVIDER_ORDER="anthropic,openai"))
    assert config.agent == "openrouter:anthropic/claude-haiku-5.5"
    assert config.judge == "openrouter:openai/gpt-6.1-sol"
    assert config.warnings == ()


def test_openrouter_judge_skips_agent_family():
    config = resolve_models(env(OPENROUTER, AGENT_MODEL="openrouter:openai/gpt-6-luna"))
    assert config.judge == "openrouter:anthropic/claude-sonnet-5.5"


def test_explicit_settings_win():
    config = resolve_models(
        env(
            ANTHROPIC,
            OPENAI,
            AGENT_MODEL="openai:gpt-6-luna",
            TRIAGE_MODEL="anthropic:claude-sonnet-5-5",
            JUDGE_MODEL="anthropic:claude-haiku-5-5",
        )
    )
    assert (config.agent, config.triage, config.judge) == (
        "openai:gpt-6-luna",
        "anthropic:claude-sonnet-5-5",
        "anthropic:claude-haiku-5-5",
    )


def test_explicit_same_family_judge_warns():
    config = resolve_models(env(ANTHROPIC, OPENAI, JUDGE_MODEL="anthropic:claude-sonnet-5-5"))
    assert any("self-preference" in w for w in config.warnings)


def test_explicit_model_without_its_key_is_an_error():
    with pytest.raises(ConfigError, match="OPENAI_API_KEY"):
        resolve_models(env(ANTHROPIC, AGENT_MODEL="openai:gpt-6-luna"))


@pytest.mark.parametrize("bad", ["claude-haiku-5-5", "anthropic:", "bedrock:claude"])
def test_malformed_model_string_is_an_error(bad):
    with pytest.raises(ConfigError):
        resolve_models(env(ANTHROPIC, AGENT_MODEL=bad))


def test_unpinned_openrouter_warns():
    config = resolve_models(OPENROUTER)
    assert any("OPENROUTER_PROVIDER_ORDER" in w for w in config.warnings)


@pytest.mark.parametrize(
    ("model", "family"),
    [
        ("anthropic:claude-haiku-5-5", "anthropic"),
        ("google_genai:gemini-3.8-flash", "google"),
        ("openrouter:openai/gpt-6-luna", "openai"),
        ("openrouter:google/gemini-4-argon", "google"),
    ],
)
def test_model_family_is_the_maker_not_the_api(model, family):
    assert model_family(model) == family


def test_openrouter_model_is_pinned_without_fallbacks(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    config = resolve_models(env(OPENROUTER, OPENROUTER_PROVIDER_ORDER="anthropic, openai"))
    model = build_chat_model(config.agent, config)
    assert type(model).__name__ == "ChatOpenRouter"
    assert model.openrouter_provider == {"order": ["anthropic", "openai"], "allow_fallbacks": False}
    assert model.temperature == 0


@pytest.mark.parametrize(
    ("keys", "expected_class"),
    [
        (ANTHROPIC, "ChatAnthropic"),
        (OPENAI, "ChatOpenAI"),
        (GOOGLE, "ChatGoogleGenerativeAI"),
    ],
)
def test_builds_the_right_chat_class(monkeypatch, keys, expected_class):
    for name, value in keys.items():
        monkeypatch.setenv(name, value)
    config = resolve_models(keys)
    model = build_chat_model(config.agent, config)
    assert type(model).__name__ == expected_class
    assert model.temperature == 0


def test_structured_method_is_opt_in_and_validated():
    from counterwrench.config import structured_kwargs

    assert structured_kwargs({}) == {}  # the default every earlier experiment used
    assert structured_kwargs({"TRIAGE_STRUCTURED_METHOD": " json_schema "}) == {
        "method": "json_schema"
    }
    with pytest.raises(ConfigError, match="json_schema or function_calling"):
        structured_kwargs({"TRIAGE_STRUCTURED_METHOD": "magic"})
