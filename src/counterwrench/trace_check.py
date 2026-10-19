"""`make trace-check`: prove tracing works end to end.

Makes one tiny traced call with full run metadata, then reads the run back from LangSmith
and checks the metadata arrived. A trace that silently fails to upload looks exactly like
success, so this verifies the effect rather than the setting.
"""

from __future__ import annotations

import os
import sys
import uuid

from counterwrench.config import ConfigError, build_chat_model, load_config
from counterwrench.tracing import run_metadata, run_url, wait_for_run

REQUIRED_KEYS = ("agent_model", "openrouter_provider_order", "git_commit", "search_mode")
READ_BACK_TIMEOUT_S = 60


def main() -> int:
    try:
        config = load_config()  # also configures tracing
    except ConfigError as exc:
        print(f"FAIL: {exc}")
        return 1

    if os.environ.get("LANGSMITH_TRACING") != "true":
        print("FAIL: tracing is off. Set LANGSMITH_API_KEY in .env (see .env.example).")
        return 1

    run_id = uuid.uuid4()
    metadata = run_metadata(config, purpose="trace-check")
    build_chat_model(config.agent, config).invoke(
        "Reply with just: ok",
        config={"run_id": run_id, "run_name": "trace-check", "metadata": metadata,
                "tags": ["trace-check"]},
    )  # fmt: skip
    client, run = wait_for_run(run_id, READ_BACK_TIMEOUT_S)
    if run is None:
        print(f"FAIL: run {run_id} never appeared in LangSmith.")
        return 1

    stored = (run.extra or {}).get("metadata", {})
    missing = [key for key in REQUIRED_KEYS if key not in stored]
    print(f"Run:     {run_url(client, run)}")
    print(f"Project: {os.environ.get('LANGSMITH_PROJECT')}")
    for key in (*REQUIRED_KEYS, "git_dirty", "ls_provider", "ls_model_name"):
        print(f"  {key:<26} {stored.get(key, '(missing)')}")
    if missing:
        print(f"FAIL: metadata missing from the stored run: {missing}")
        return 1
    print("Trace verified: written and read back with its metadata.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
