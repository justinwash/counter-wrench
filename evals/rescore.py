"""`make eval-rescore EXP=<experiment>`: re-score a past experiment against the current labels.

When labels change (step 16 corrected 17 cases), old experiments stop being comparable with new
ones. The code evaluators are pure functions of (run output, labels, catalog), so an experiment's
saved run outputs can be re-scored without calling the agent again. Judge scores are reused as
recorded: re-judging would cost money and change two variables at once.
"""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor

from dotenv import find_dotenv, load_dotenv
from langsmith import Client

from evals.datasets.schema import load_e2e
from evals.datasets.upload import E2E_DATASET, example_uuid
from evals.evaluators import Reference, load_catalog
from evals.report import run_scores, safety_misses, table
from evals.run_output import RunOutput
from evals.runner import DETERMINISTIC

JUDGES = ("diagnosis_reasonable", "explanation_quality")


def rescore(client: Client, experiment: str) -> list[dict]:
    examples = {str(example_uuid(E2E_DATASET, e.id)): e for e in load_e2e()}
    runs = sorted(
        (r for r in client.list_runs(project_name=experiment, is_root=True) if not r.error),
        key=lambda r: r.start_time,
    )  # an errored run has no output to score (report.py lists them)
    with ThreadPoolExecutor(max_workers=8) as pool:
        recorded = list(pool.map(lambda r: run_scores(client, r.id), runs))
    ctx, rows, seen = load_catalog(), [], {}
    for run, old in zip(runs, recorded, strict=True):
        example = examples[str(run.reference_example_id)]
        out = RunOutput.model_validate(run.outputs["run"])
        ref = Reference.from_example(example)
        scores = {s.key: s.score for s in (f(out, ref, ctx) for f in DETERMINISTIC)}
        missing = [k for k in JUDGES if k not in old]
        if missing:
            print(f"MISSING {run.id}: {', '.join(missing)} (not recorded)", file=sys.stderr)
        scores.update({k: old[k] for k in JUDGES if k in old})
        rep = seen.get(example.id, 0)
        seen[example.id] = rep + 1
        rows.append({"case": example.id, "slice": example.slice, "rep": rep, "scores": scores})
    return rows


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python -m evals.rescore <experiment name>")
        return 2
    load_dotenv(find_dotenv(usecwd=True))
    rows = rescore(Client(), sys.argv[1])
    print(f"{len(rows)} runs re-scored against the current labels (judge scores as recorded)\n")
    print(table(rows))
    print("\nSafety misses:\n")
    print(safety_misses(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
