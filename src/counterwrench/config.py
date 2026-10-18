"""Model configuration: which model plays each role, and how to build it.

Every other module asks this one for models; nothing else names a model ID.
Resolution is a pure function of an env mapping so every rule is unit-testable
without API keys or network access.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)

Role = Literal["agent", "triage", "judge"]

# Auto-detect priority order: the first provider with a key supplies the defaults.
PROVIDER_KEYS: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google_genai": "GOOGLE_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}

# Per-provider defaults: a cheap capable model for agent and triage, a stronger one for the judge.
DEFAULTS: dict[str, dict[str, str]] = {
    "anthropic": {"cheap": "claude-haiku-5-5", "strong": "claude-sonnet-5-5"},
    "openai": {"cheap": "gpt-6-luna", "strong": "gpt-6.1-sol"},
    "google_genai": {"cheap": "gemini-3.5-flash-lite", "strong": "gemini-4-argon"},
    "openrouter": {"cheap": "anthropic/claude-haiku-5.5", "strong": "openai/gpt-6.1-sol"},
}

# OpenRouter serves several model families, so it can supply a cross-family judge on its own.
OPENROUTER_JUDGES: tuple[str, ...] = (
    "openai/gpt-6.1-sol",
    "anthropic/claude-sonnet-5.5",
    "google/gemini-4-argon",
)

_FAMILY_BY_PROVIDER = {"anthropic": "anthropic", "openai": "openai", "google_genai": "google"}


class ConfigError(Exception):
    """Configuration can't produce a usable model; the message says how to fix it."""


@dataclass(frozen=True)
class ModelConfig:
    agent: str
    triage: str
    judge: str
    available_providers: tuple[str, ...]
    openrouter_provider_order: tuple[str, ...]
    warnings: tuple[str, ...]

    def model_for(self, role: Role) -> str:
        return getattr(self, role)


def split_model(model: str) -> tuple[str, str]:
    """Split 'provider:model' on the first colon (OpenRouter IDs can contain more)."""
    provider, sep, name = model.partition(":")
    if not sep or not name:
        raise ConfigError(f"Model {model!r} must be 'provider:model', e.g. 'anthropic:<model>'.")
    if provider not in PROVIDER_KEYS:
        raise ConfigError(
            f"Unknown provider {provider!r} in {model!r}. Use one of: {', '.join(PROVIDER_KEYS)}."
        )
    return provider, name


def model_family(model: str) -> str:
    """Who made the model, not which API serves it: 'openrouter:anthropic/x' is 'anthropic'."""
    provider, name = split_model(model)
    if provider == "openrouter":
        return name.split("/", 1)[0]
    return _FAMILY_BY_PROVIDER[provider]


def detect_providers(env: Mapping[str, str]) -> tuple[str, ...]:
    return tuple(p for p, key in PROVIDER_KEYS.items() if env.get(key, "").strip())


def resolve_models(env: Mapping[str, str]) -> ModelConfig:
    available = detect_providers(env)
    if not available:
        raise ConfigError(
            "No LLM provider key found. Set one of "
            + ", ".join(PROVIDER_KEYS.values())
            + " in .env (see .env.example)."
        )
    warnings: list[str] = []
    primary = available[0]

    def explicit(var: str) -> str | None:
        value = env.get(var, "").strip()
        if not value:
            return None
        provider, _ = split_model(value)
        if provider not in available:
            raise ConfigError(f"{var}={value} needs {PROVIDER_KEYS[provider]}, which isn't set.")
        return value

    agent = explicit("AGENT_MODEL") or f"{primary}:{DEFAULTS[primary]['cheap']}"
    triage = explicit("TRIAGE_MODEL") or f"{primary}:{DEFAULTS[primary]['cheap']}"

    judge = explicit("JUDGE_MODEL")
    if judge is None:
        judge = _pick_judge(agent, available)
    if model_family(judge) == model_family(agent):
        warnings.append(
            f"Judge ({judge}) and agent ({agent}) are the same model family; "
            "self-preference bias applies. Add a second provider key for a cross-family judge."
        )

    raw_order = env.get("OPENROUTER_PROVIDER_ORDER", "").split(",")
    order = tuple(p.strip() for p in raw_order if p.strip())
    uses_openrouter = any(split_model(m)[0] == "openrouter" for m in (agent, triage, judge))
    if uses_openrouter and not order:
        warnings.append(
            "OpenRouter is in use but OPENROUTER_PROVIDER_ORDER is blank, so the serving backend "
            "can change between runs. Pin it for reproducible eval comparisons."
        )

    return ModelConfig(
        agent=agent,
        triage=triage,
        judge=judge,
        available_providers=available,
        openrouter_provider_order=order,
        warnings=tuple(warnings),
    )


def _pick_judge(agent: str, available: tuple[str, ...]) -> str:
    """Strong model from a different family than the agent; same family only as a last resort."""
    candidates = [f"{p}:{DEFAULTS[p]['strong']}" for p in available if p != "openrouter"]
    if "openrouter" in available:
        candidates += [f"openrouter:{m}" for m in OPENROUTER_JUDGES]
    agent_family = model_family(agent)
    for candidate in candidates:
        if model_family(candidate) != agent_family:
            return candidate
    agent_provider, _ = split_model(agent)
    return f"{agent_provider}:{DEFAULTS[agent_provider]['strong']}"


def build_chat_model(model: str, config: ModelConfig) -> BaseChatModel:
    """Build (without calling) the chat model. Temperature 0; OpenRouter pinned when configured."""
    provider, name = split_model(model)
    kwargs: dict = {"temperature": 0}
    if provider == "openrouter" and config.openrouter_provider_order:
        kwargs["openrouter_provider"] = {
            "order": list(config.openrouter_provider_order),
            "allow_fallbacks": False,
        }
    return init_chat_model(name, model_provider=provider, **kwargs)


def load_config() -> ModelConfig:
    """Load .env into the process environment (real env vars win), then resolve."""
    load_dotenv(override=False)
    config = resolve_models(os.environ)
    for warning in config.warnings:
        logger.warning(warning)
    return config


def get_chat_model(role: Role, config: ModelConfig | None = None) -> BaseChatModel:
    config = config or load_config()
    return build_chat_model(config.model_for(role), config)
