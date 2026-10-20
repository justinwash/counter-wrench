"""`make eval-report EXP=<experiment>`: an experiment's scores as markdown for EVAL_RESULTS.md.

Per slice and evaluator: the mean over all runs, and the spread (max - min) of the per-repetition
means, so a before/after gap can be compared with run-to-run noise. Safety misses are listed
case by case, never averaged away.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from dotenv import find_dotenv, load_dotenv
from langsmith import Client

from evals.datasets.schema import load_e2e
from evals.datasets.upload import E2E_DATASET, example_uuid
from evals.queue import SAFETY_KEYS

SLICES = ["normal", "edge", "staff_misattribution", "note_contradicts_picklist", "safety",
          "adversarial"]  # fmt: skip


def run_scores(client: Client, run_id) -> dict[str, float | None]:
    # One run per query: list_feedback over many run ids pages unstably (duplicates some
    # feedback and drops other), which silently corrupted the first E-001 table.
    return {f.key: f.score for f in client.list_feedback(run_ids=[run_id])}


def collect(client: Client, experiment: str) -> list[dict]:
    """One dict per run: case, slice, repetition (by start time within the case), scores.
    Raises if any run is missing an evaluator's score, rather than report partial data."""
    examples = {str(example_uuid(E2E_DATASET, e.id)): e for e in load_e2e()}
    runs = list(client.list_runs(project_name=experiment, is_root=True))
    with ThreadPoolExecutor(max_workers=8) as pool:
        fetched = pool.map(lambda r: run_scores(client, r.id), runs)
    scores = {str(r.id): s for r, s in zip(runs, fetched, strict=True)}
    expected = set().union(*scores.values()) - {"queue_note"}
    incomplete = [run_id for run_id, s in scores.items() if not expected <= set(s)]
    if incomplete:
        raise RuntimeError(f"{len(incomplete)} runs are missing scores (ingestion lag?); retry")
    rows, seen = [], defaultdict(int)
    for run in sorted(runs, key=lambda r: r.start_time):
        example = examples[str(run.reference_example_id)]
        rows.append({"case": example.id, "slice": example.slice, "rep": seen[example.id],
                     "scores": scores[str(run.id)]})  # fmt: skip
        seen[example.id] += 1
    return rows


def table(rows: list[dict]) -> str:
    # values[key][slice][rep] -> scores
    values = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for row in rows:
        for key, score in row["scores"].items():
            if score is not None and key != "queue_note":
                values[key][row["slice"]][row["rep"]].append(score)
    header = "| Evaluator | " + " | ".join(s.replace("_", " ") for s in SLICES) + " |"
    lines = [header, "|---" * (len(SLICES) + 1) + "|"]
    for key in sorted(values, key=lambda k: (k not in SAFETY_KEYS, k)):
        cells = []
        for slice_name in SLICES:
            reps = values[key].get(slice_name)
            if not reps:
                cells.append("–")
                continue
            everything = [v for vs in reps.values() for v in vs]
            means = [sum(vs) / len(vs) for vs in reps.values()]
            cells.append(f"{sum(everything) / len(everything):.2f} ±{max(means) - min(means):.2f}")
        lines.append(f"| {key} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def safety_misses(rows: list[dict]) -> str:
    by_case = defaultdict(lambda: defaultdict(int))
    reps = defaultdict(int)
    for row in rows:
        reps[row["case"]] += 1
        for key in SAFETY_KEYS:
            if row["scores"].get(key) == 0:
                by_case[row["case"]][key] += 1
    if not by_case:
        return "No safety misses."
    return "\n".join(
        f"- {case}: " + ", ".join(f"{k} failed {n}/{reps[case]}" for k, n in sorted(keys.items()))
        for case, keys in sorted(by_case.items())
    )


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python -m evals.report <experiment name>")
        return 2
    load_dotenv(find_dotenv(usecwd=True))
    rows = collect(Client(), sys.argv[1])
    print(f"{len(rows)} runs\n\nMean ±spread (max - min of the per-repetition means):\n")
    print(table(rows))
    print("\nSafety misses:\n")
    print(safety_misses(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
