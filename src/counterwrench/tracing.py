"""LangSmith tracing: on automatically when a key is present, off (silently) when it isn't.

Also builds the metadata every run records, so experiments are comparable: which models,
which pinned OpenRouter backends, which code (git commit), which retrieval setup.
"""

from __future__ import annotations

import os
import subprocess
import time
import warnings
from collections.abc import MutableMapping
from functools import cache
from pathlib import Path
from typing import Any

DEFAULT_PROJECT = "counterwrench-dev"
REPO_ROOT = Path(__file__).resolve().parents[2]


def configure_tracing(env: MutableMapping[str, str] = os.environ) -> bool:
    """Tracing is on when LANGSMITH_API_KEY is set, unless LANGSMITH_TRACING=false opts out.
    Without a key it's forced off, so no upload attempts fail with 401s. Call before any
    LangChain or LangSmith code runs: LangSmith caches these settings on first read."""
    has_key = bool(env.get("LANGSMITH_API_KEY", "").strip())
    opted_out = env.get("LANGSMITH_TRACING", "").strip().lower() == "false"
    enabled = has_key and not opted_out
    env["LANGSMITH_TRACING"] = "true" if enabled else "false"
    if enabled and not env.get("LANGSMITH_PROJECT", "").strip():
        env["LANGSMITH_PROJECT"] = DEFAULT_PROJECT
    return enabled


@cache
def git_version() -> dict[str, Any]:
    """The commit is the prompt/graph version: any prompt or graph change is a commit.
    `dirty` flags runs made on uncommitted code."""

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()

    try:
        return {
            "git_commit": git("rev-parse", "--short", "HEAD"),
            "git_dirty": bool(git("status", "--porcelain")),
        }
    except (OSError, subprocess.CalledProcessError):
        return {"git_commit": "unknown", "git_dirty": None}


def run_metadata(config, **extra: Any) -> dict[str, Any]:
    """Metadata attached to every traced run. `config` is a ModelConfig."""
    from counterwrench.rag.embed import MODEL_NAME
    from counterwrench.rag.search import DEFAULT_MODE

    return {
        "agent_model": config.agent,
        "triage_model": config.triage,
        "judge_model": config.judge,
        "openrouter_provider_order": list(config.openrouter_provider_order),
        "search_mode": str(DEFAULT_MODE),
        "embedding_model": MODEL_NAME,
        **git_version(),
        **extra,
    }


# read_run/get_run_url are deprecated in favor of client.runs.retrieve()/get_url(), which need
# a project ID, trace ID and field list. The old calls work until 2027-01-31; migrate before then.
def read_run(client, run_id):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        return client.read_run(run_id)


def run_url(client, run) -> str:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        return client.get_run_url(run=run)


def wait_for_run(run_id, timeout_s: float = 60):
    """Flush pending traces, then poll LangSmith until the run is readable. None on timeout."""
    from langchain_core.tracers.langchain import wait_for_all_tracers
    from langsmith import Client
    from langsmith.utils import LangSmithNotFoundError

    wait_for_all_tracers()
    client, deadline = Client(), time.monotonic() + timeout_s
    while True:
        try:
            return client, read_run(client, run_id)
        except LangSmithNotFoundError:
            if time.monotonic() > deadline:
                return client, None
            time.sleep(2)


def trace_url(run_id, timeout_s: float = 60) -> str | None:
    """Link to a run's trace, or None when tracing is off or the run never arrived."""
    if os.environ.get("LANGSMITH_TRACING") != "true":
        return None
    client, run = wait_for_run(run_id, timeout_s)
    return run_url(client, run) if run else None
