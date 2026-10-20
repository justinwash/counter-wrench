"""`make eval`: run the agent over the LangSmith datasets and score every run (D-034).

Official runs need a clean git tree (the commit is the prompt/graph version); `--scratch` allows
a dirty tree and prefixes the experiment name. Before anything is spent, the configured models
are checked once and the exact OpenRouter snapshot and backend go into the experiment metadata.

    uv run python -m evals.runner                       # official: e2e x3 + retrieval
    uv run python -m evals.runner --scratch --limit 6   # pilot: one case per slice, once
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import uuid
from collections import defaultdict
from itertools import zip_longest

import httpx
from langgraph.checkpoint.memory import InMemorySaver
from langsmith import Client, evaluate

from counterwrench.agent.graph import build_graph, default_deps
from counterwrench.config import build_chat_model, load_config
from counterwrench.db.connection import connect
from counterwrench.doctor import check_structured_output, lookup_backends, verify_pinning
from counterwrench.guardrails import apply_guardrails
from counterwrench.models import IntakeForm
from counterwrench.rag.search import search_knowledge
from counterwrench.tracing import git_version, run_metadata
from evals.build_output import build_run_output
from evals.datasets.schema import load_e2e
from evals.datasets.upload import E2E_DATASET, RETRIEVAL_DATASET, example_uuid
from evals.evaluators import Reference, load_catalog, safety, trajectory, triage
from evals.evaluators import draft as draft_evals
from evals.evaluators.judge import load_rubric, make_judges
from evals.evaluators.retrieval import mrr, recall_at_k
from evals.queue import ScoredRun, push, select_failures
from evals.run_output import RunOutput

DETERMINISTIC = [*safety.EVALUATORS, *triage.EVALUATORS, *draft_evals.EVALUATORS,
                 *trajectory.EVALUATORS]  # fmt: skip
CREDITS_URL = "https://openrouter.ai/api/v1/key"


# --- Preflight -----------------------------------------------------------------------------------


def model_snapshots(config) -> dict:
    """One structured-output call per model: proves it works and records what served it."""
    results = [check_structured_output(m, config) for m in sorted({config.agent, config.triage,
                                                                     config.judge})]  # fmt: skip
    if key := os.environ.get("OPENROUTER_API_KEY"):
        lookup_backends(results, key)
        verify_pinning(results, config)
    failed = [f"{r.model}: {r.detail}" for r in results if not r.ok]
    if failed:
        raise SystemExit("Model preflight failed:\n  " + "\n  ".join(failed))
    return {r.model: {"served_by": r.served_by, "snapshot": r.snapshot} for r in results}


def credits_used() -> float | None:
    """OpenRouter credits used so far on this key, to measure an experiment's cost."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        return None
    response = httpx.get(CREDITS_URL, headers={"Authorization": f"Bearer {key}"}, timeout=10)
    return response.json()["data"]["usage"] if response.status_code == 200 else None


# --- Targets -------------------------------------------------------------------------------------


def make_agent_target(config):
    graph = build_graph(default_deps(config), checkpointer=InMemorySaver())

    def counterwrench_agent(inputs: dict) -> dict:
        # Same boundary as the CLI and API: only the redacted intake enters the graph.
        guarded = apply_guardrails(IntakeForm.model_validate(inputs["intake"]))
        flags = sorted({f.kind for f in guarded.flags})
        run_id = uuid.uuid4()
        state = graph.invoke(
            {"intake": guarded.intake, "run_id": str(run_id), "source": "eval",
             "guardrail_note": guarded.mechanic_note(), "guardrail_flags": flags},
            config={"run_id": run_id, "run_name": "counterwrench",
                    "configurable": {"thread_id": str(run_id)},
                    "metadata": {"pii_redacted": guarded.pii_counts, "guardrail_flags": flags}},
        )  # fmt: skip
        with connect() as conn:
            return {"run": build_run_output(state, conn).model_dump(mode="json")}

    return counterwrench_agent


def retrieval_target(inputs: dict) -> dict:
    with connect() as conn:
        hits = search_knowledge(conn, inputs["query"], inputs.get("bike_id"))
    return {"chunk_ids": [h.chunk_id for h in hits]}


# --- Evaluators (adapters from our pure functions to LangSmith's signature) -----------------------


def _result(score) -> dict:
    return {"key": score.key, "score": score.score, "comment": score.comment}


def deterministic(run, example) -> dict:
    out = RunOutput.model_validate(run.outputs["run"])
    ref, ctx = Reference.from_langsmith(example.inputs, example.outputs), load_catalog()
    return {"results": [_result(f(out, ref, ctx)) for f in DETERMINISTIC]}


def judge_adapters(judge_model) -> list:
    adapters = []
    for judge in make_judges(judge_model):

        def adapter(run, example, judge=judge) -> dict:
            out = RunOutput.model_validate(run.outputs["run"])
            ref = Reference.from_langsmith(example.inputs, example.outputs)
            return _result(judge(out, ref, load_catalog()))

        adapter.__name__ = adapter.__qualname__ = judge.__name__  # LangSmith names errors by it
        adapters.append(adapter)
    return adapters


def retrieval_scores(run, example) -> dict:
    got, expected = run.outputs["chunk_ids"], example.outputs["expected_chunks"]
    return {"results": [_result(recall_at_k(got, expected)), _result(mrr(got, expected))]}


# --- Running ----------------------------------------------------------------------------------


def pick_examples(client: Client, limit: int | None) -> list:
    """All examples, or `limit` spread across slices (round robin) for a pilot."""
    examples = list(client.list_examples(dataset_name=E2E_DATASET))
    if not limit:
        return examples
    by_slice = defaultdict(list)
    for ex in sorted(examples, key=lambda e: str(e.id)):
        by_slice[ex.metadata["slice"]].append(ex)
    spread = [ex for group in zip_longest(*by_slice.values()) for ex in group if ex]
    return spread[:limit]


def summarize(rows: list, case_ids: dict[str, str], slices: dict[str, str]) -> list[ScoredRun]:
    scored, by_slice = [], defaultdict(lambda: defaultdict(list))
    for row in rows:
        example_id = str(row["example"].id)
        scores = {r.key: r.score for r in row["evaluation_results"]["results"]}
        scored.append(ScoredRun(example_id, case_ids.get(example_id, example_id),
                                str(row["run"].id), scores))  # fmt: skip
        for key, value in scores.items():
            if value is not None:
                by_slice[slices[example_id]][key].append(value)
    print("\nMean score by slice (n = scored runs):")
    for slice_name, keys in sorted(by_slice.items()):
        print(f"  {slice_name}")
        for key, values in sorted(keys.items()):
            print(f"    {key:30} {sum(values) / len(values):.2f}  (n={len(values)})")
    return scored


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m evals.runner")
    parser.add_argument("--scratch", action="store_true", help="allow a dirty tree; label it")
    parser.add_argument("--limit", type=int, help="only this many e2e cases, spread by slice")
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--no-queue", action="store_true", help="don't queue failing cases")
    args = parser.parse_args()

    config = load_config()
    version = git_version()
    if version["git_dirty"] and not args.scratch:
        print("Refusing an official run on uncommitted code: commit first, or pass --scratch.")
        return 1
    if os.environ.get("LANGSMITH_TRACING") != "true":
        print("Evals need LangSmith: set LANGSMITH_API_KEY in .env.")
        return 1

    print("Preflight: checking each model once...")
    snapshots = model_snapshots(config)
    prefix = f"{'scratch-' if args.scratch else ''}{version['git_commit']}"
    metadata = run_metadata(
        config, model_snapshots=snapshots, repetitions=args.repetitions, scratch=args.scratch,
        rubric_versions={n: load_rubric(n).version
                         for n in ("diagnosis_reasonable", "explanation_quality")},
    )  # fmt: skip

    client = Client()
    print("Retrieval experiment (no LLM calls)...")
    evaluate(retrieval_target, data=RETRIEVAL_DATASET, evaluators=[retrieval_scores],
             experiment_prefix=f"{prefix}-retrieval", metadata=metadata, client=client)  # fmt: skip

    examples = pick_examples(client, args.limit)
    case_ids = {str(example_uuid(E2E_DATASET, ex.id)): ex.id for ex in load_e2e()}
    slices = {str(ex.id): ex.metadata["slice"] for ex in examples}
    judge_model = build_chat_model(config.judge, config)
    print(f"E2E experiment: {len(examples)} cases x {args.repetitions} repetitions...")
    before, started = credits_used(), time.monotonic()
    results = evaluate(
        make_agent_target(config), data=examples,
        evaluators=[deterministic, *judge_adapters(judge_model)],
        experiment_prefix=f"{prefix}-e2e", metadata={**metadata, "cases": len(examples)},
        num_repetitions=args.repetitions, max_concurrency=args.concurrency, client=client,
    )  # fmt: skip
    rows = list(results)
    minutes = (time.monotonic() - started) / 60
    time.sleep(5)  # credit usage lags the last calls slightly
    after = credits_used()

    scored = summarize(rows, case_ids, slices)
    items = select_failures(scored)
    print(f"\nFailing cases: {len(items)} of {len(examples)}")
    for item in items:
        print(f"  {item.case}: {item.note()}")
    errors = sum(1 for r in rows if r["run"].error)
    print(f"\nRuns: {len(rows)} ({errors} errored), {minutes:.1f} min")
    if before is not None and after is not None:
        cost = after - before
        print(f"Cost: ${cost:.3f} total, ${cost / max(len(rows), 1):.4f} per run (incl. judges)")
    print(f"Experiment: {results.experiment_name}")
    if items and not args.no_queue and not args.scratch:
        queue_id = push(client, items, results.experiment_name)
        print(f"Queued {len(items)} cases for review (annotation queue {queue_id}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
