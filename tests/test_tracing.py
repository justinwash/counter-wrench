import pytest

from counterwrench.config import resolve_models
from counterwrench.tracing import configure_tracing, git_version, run_metadata


@pytest.mark.parametrize(
    ("env", "enabled"),
    [
        ({"LANGSMITH_API_KEY": "lsv2"}, True),  # key alone turns it on
        ({"LANGSMITH_API_KEY": "lsv2", "LANGSMITH_TRACING": "true"}, True),
        ({"LANGSMITH_API_KEY": "lsv2", "LANGSMITH_TRACING": "False"}, False),  # opt out
        ({"LANGSMITH_TRACING": "true"}, False),  # no key: forced off, no 401 noise
        ({"LANGSMITH_API_KEY": "  "}, False),  # blank key counts as missing
        ({}, False),
    ],
)
def test_configure_tracing(env, enabled):
    assert configure_tracing(env) is enabled
    assert env["LANGSMITH_TRACING"] == ("true" if enabled else "false")


def test_default_project_only_when_unset():
    env = {"LANGSMITH_API_KEY": "k", "LANGSMITH_PROJECT": ""}
    configure_tracing(env)
    assert env["LANGSMITH_PROJECT"] == "counterwrench-dev"
    env = {"LANGSMITH_API_KEY": "k", "LANGSMITH_PROJECT": "mine"}
    configure_tracing(env)
    assert env["LANGSMITH_PROJECT"] == "mine"


def test_run_metadata_records_what_makes_runs_comparable():
    config = resolve_models(
        {"OPENROUTER_API_KEY": "k", "OPENROUTER_PROVIDER_ORDER": "anthropic,openai"}
    )
    meta = run_metadata(config, purpose="test")
    assert meta["agent_model"] == "openrouter:anthropic/claude-haiku-5.5"
    assert meta["openrouter_provider_order"] == ["anthropic", "openai"]
    assert meta["search_mode"] == "vector"
    assert meta["embedding_model"] == "BAAI/bge-small-en-v1.5"
    assert meta["purpose"] == "test"
    assert {"git_commit", "git_dirty"} <= meta.keys()


def test_git_version_reads_this_repo():
    version = git_version()
    assert version["git_commit"] != "unknown"
    assert isinstance(version["git_dirty"], bool)
