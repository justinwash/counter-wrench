"""`make doctor`: check that the configured models actually work before spending money on evals.

Prints the resolved setup (key names only, never values), then makes one tool-calling and one
structured-output call per unique model. For OpenRouter models it also reports which backend
served each call and the exact dated snapshot, so pinning is verified rather than assumed.
Exits nonzero with a fix hint if anything fails.
"""

from __future__ import annotations

import os
import re
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass

import httpx
from dotenv import find_dotenv, load_dotenv
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from pydantic import BaseModel

from counterwrench.config import (
    PROVIDER_KEYS,
    ConfigError,
    ModelConfig,
    build_chat_model,
    resolve_models,
    split_model,
)
from counterwrench.models import Severity
from counterwrench.tracing import configure_tracing

# Overrides that silently redirect provider SDKs (e.g. a local proxy inherited from the shell).
BASE_URL_VARS = ("ANTHROPIC_BASE_URL", "ANTHROPIC_API_URL", "OPENAI_BASE_URL", "OPENAI_API_BASE")

GENERATION_URL = "https://openrouter.ai/api/v1/generation"
GENERATION_TIMEOUT_S = 30


@tool
def lookup_labor_price(code: str) -> str:
    """Look up the shop's flat labor price for a service menu code, e.g. 'BRAKE-BLEED'."""
    return "45.00"


class SeverityCheck(BaseModel):
    severity: Severity
    reason: str


TOOL_PROMPT = "What does the shop charge for labor code BRAKE-BLEED? Use the tool to find out."
STRUCTURED_PROMPT = (
    "A customer's front brake lever pulls all the way to the handlebar without stopping the "
    "wheel. Classify the severity of this bike repair issue."
)


@dataclass
class CheckResult:
    model: str
    check: str
    ok: bool
    seconds: float
    detail: str
    generation_id: str | None = None
    served_by: str | None = None
    snapshot: str | None = None


def unique_models(config: ModelConfig) -> dict[str, list[str]]:
    """Map each distinct model to the roles that use it, so shared models are called once."""
    models: dict[str, list[str]] = {}
    for role in ("agent", "triage", "judge"):
        models.setdefault(config.model_for(role), []).append(role)
    return models


def describe_env(env: Mapping[str, str]) -> list[str]:
    """Report which keys and overrides are set. Never includes values."""
    lines = []
    for var in PROVIDER_KEYS.values():
        state = "set" if env.get(var, "").strip() else "-"
        lines.append(f"  {var:<20} {state}")
    for var in BASE_URL_VARS:
        if env.get(var, "").strip():
            lines.append(
                f"  {var:<20} SET: provider calls are redirected; unset it unless intended"
            )
    return lines


def _validate_langsmith_key() -> None:
    """One lightweight authenticated call; raises if the key is rejected."""
    from langsmith import Client

    next(iter(Client().list_projects(limit=1)), None)


def langsmith_status(
    env: Mapping[str, str], validate: Callable[[], None] = _validate_langsmith_key
) -> tuple[str, bool]:
    """Return (description, ok), after configure_tracing() has run."""
    if env.get("LANGSMITH_TRACING") != "true":
        if env.get("LANGSMITH_API_KEY", "").strip():
            return "tracing off (LANGSMITH_TRACING=false)", True
        return "tracing off: no LANGSMITH_API_KEY (fine for running the agent; evals need it)", True
    try:
        validate()
    except Exception as exc:
        return f"LANGSMITH_API_KEY was rejected ({type(exc).__name__}); check it in .env", False
    return f"tracing on, key valid, project '{env.get('LANGSMITH_PROJECT')}'", True


def fix_hint(exc: BaseException, model: str) -> str:
    """Turn a provider error into a one-line fix. Providers raise different exception types,
    so this keys off the HTTP status where available and the message otherwise."""
    provider, _ = split_model(model)
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    text = str(exc)
    if status is None:
        match = re.search(r"\b(401|402|403|404|429)\b", text)
        status = int(match.group(1)) if match else None
    if status == 401:
        return f"Authentication failed: check {PROVIDER_KEYS[provider]} in .env."
    if status == 402:
        return "Out of credits: top up the account or raise the key's credit limit."
    if status == 404:
        return f"Model not found: check the ID in {model!r} or override it in .env."
    if status == 429:
        return "Rate limited: wait and re-run."
    if "structured" in text.lower() or "response_format" in text.lower():
        return "Backend can't do structured output: pin OPENROUTER_PROVIDER_ORDER to one that can."
    return f"Unexpected error: {type(exc).__name__}: {text[:200]}"


def normalize_provider(name: str) -> str:
    """'Amazon Bedrock' -> 'amazon-bedrock', to compare with OPENROUTER_PROVIDER_ORDER slugs."""
    return name.strip().lower().replace(" ", "-")


def _generation_id(message: AIMessage) -> str | None:
    return message.response_metadata.get("id")


def check_tool_calling(model: str, config: ModelConfig) -> CheckResult:
    start = time.perf_counter()
    try:
        llm = build_chat_model(model, config).bind_tools([lookup_labor_price])
        message = llm.invoke(TOOL_PROMPT)
    except Exception as exc:
        return CheckResult(
            model, "tool calling", False, time.perf_counter() - start, fix_hint(exc, model)
        )
    seconds = time.perf_counter() - start
    calls = [c for c in message.tool_calls if c["name"] == "lookup_labor_price"]
    if not calls or "code" not in calls[0]["args"]:
        return CheckResult(
            model, "tool calling", False, seconds, "model answered without calling the tool"
        )
    detail = f"called lookup_labor_price(code={calls[0]['args']['code']!r})"
    return CheckResult(model, "tool calling", True, seconds, detail, _generation_id(message))


def check_structured_output(model: str, config: ModelConfig) -> CheckResult:
    start = time.perf_counter()
    try:
        llm = build_chat_model(model, config).with_structured_output(
            SeverityCheck, include_raw=True
        )
        result = llm.invoke(STRUCTURED_PROMPT)
    except Exception as exc:
        return CheckResult(
            model, "structured output", False, time.perf_counter() - start, fix_hint(exc, model)
        )
    seconds = time.perf_counter() - start
    gen_id = _generation_id(result["raw"])
    parsed = result["parsed"]
    if not isinstance(parsed, SeverityCheck):
        error = result.get("parsing_error")
        return CheckResult(
            model, "structured output", False, seconds, f"didn't parse: {error}", gen_id
        )
    return CheckResult(
        model, "structured output", True, seconds, f"severity={parsed.severity}", gen_id
    )


def lookup_backends(results: list[CheckResult], api_key: str) -> None:
    """Fill in served_by/snapshot for OpenRouter calls. Generation stats appear after a few
    seconds, so poll until each is available or the timeout passes."""
    pending = [r for r in results if r.generation_id and split_model(r.model)[0] == "openrouter"]
    deadline = time.monotonic() + GENERATION_TIMEOUT_S
    with httpx.Client(headers={"Authorization": f"Bearer {api_key}"}, timeout=10) as client:
        while pending and time.monotonic() < deadline:
            for result in list(pending):
                response = client.get(GENERATION_URL, params={"id": result.generation_id})
                if response.status_code == 200:
                    data = response.json()["data"]
                    result.served_by = data.get("provider_name")
                    result.snapshot = data.get("model")
                    pending.remove(result)
            if pending:
                time.sleep(1)


def verify_pinning(results: list[CheckResult], config: ModelConfig) -> None:
    """Fail any OpenRouter check that couldn't be traced, or that ran outside the pinned order."""
    allowed = {normalize_provider(p) for p in config.openrouter_provider_order}
    for result in results:
        if not result.ok or split_model(result.model)[0] != "openrouter":
            continue
        if result.served_by is None:
            result.ok = False
            result.detail += "; couldn't confirm the serving backend (generation stats timed out)"
        elif allowed and normalize_provider(result.served_by) not in allowed:
            result.ok = False
            result.detail += f"; served by {result.served_by}, outside OPENROUTER_PROVIDER_ORDER"


def main() -> int:
    env_path = find_dotenv(usecwd=True)
    load_dotenv(env_path, override=False)
    configure_tracing(os.environ)
    env = os.environ

    print("CounterWrench doctor\n")
    print(f".env: {env_path or 'not found (using process environment only)'}")
    print("Keys:")
    print("\n".join(describe_env(env)))

    try:
        config = resolve_models(env)
    except ConfigError as exc:
        print(f"\nFAIL: {exc}")
        return 1

    print("\nModels:")
    models = unique_models(config)
    for model, roles in models.items():
        print(f"  {', '.join(roles):<20} {model}")
    if config.openrouter_provider_order:
        order = ", ".join(config.openrouter_provider_order)
        print(f"  OpenRouter order     {order} (fallbacks off)")
    for warning in config.warnings:
        print(f"  WARNING: {warning}")

    tracing, tracing_ok = langsmith_status(env)
    print(f"\nLangSmith: {tracing}")

    # Doctor's own test calls aren't worth tracing; keep them out of the LangSmith project.
    os.environ["LANGSMITH_TRACING"] = "false"

    print("\nLive checks:")
    results: list[CheckResult] = []
    for model in models:
        results.append(check_tool_calling(model, config))
        results.append(check_structured_output(model, config))
    if "openrouter" in config.available_providers:
        lookup_backends(results, env["OPENROUTER_API_KEY"])
        verify_pinning(results, config)

    for r in results:
        status = "PASS" if r.ok else "FAIL"
        print(f"  {status}  {r.model}  {r.check} ({r.seconds:.1f}s): {r.detail}")
        if r.served_by:
            print(f"        served by {r.served_by}, snapshot {r.snapshot}")

    ok = tracing_ok and all(r.ok for r in results)
    print("\nAll checks passed." if ok else "\nDoctor found problems; see FAIL lines above.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
