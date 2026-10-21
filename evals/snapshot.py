"""`make evals-snapshot`: freeze the experiment results into a file the app can show.

The Evals pages must work on a fresh clone with no LangSmith key, so they read this committed
snapshot instead of querying LangSmith. Every experiment is re-scored against the *current*
labels (evals/rescore.py: the code evaluators are re-run on the saved outputs, the judge scores
are as recorded), so the columns compare directly. Regenerate after any new experiment or
label change; the page shows when it was last generated.
"""

from __future__ import annotations

import json
import subprocess
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from langsmith import Client

from evals.queue import SAFETY_KEYS
from evals.rescore import rescore

OUT = Path(__file__).parent / "snapshot" / "results.json"
SEVERITIES = [
    "safety_critical",
    "needs_service",
    "needs_adjustment",
    "cosmetic",
    "no_action_needed",
]
SLICES = ["normal", "edge", "staff_misattribution", "note_contradicts_picklist", "safety",
          "adversarial"]  # fmt: skip
JUDGES = ("diagnosis_reasonable", "explanation_quality")

# id, LangSmith experiment, what changed (one variable each), the doc section
EXPERIMENTS = [
    ("E-001b", "4b0e975-e2e-987f108b", "Baseline (v0 agent), re-scored on the corrected labels"),
    ("E-002", "498e073-e2e-8da1f14b", "The never-release list always reaches triage"),
    ("E-003", "3fca1d3-e2e-4e515072", "Row questions go on the draft instead of stopping the run"),
    ("E-004", "15bdd8e-e2e-819a899d", "draft_work_order enforces line coherence"),
    ("E-005", "d0c598b-e2e-9b1caa49", "Agreement with staff comes from the agent's own area pick"),
    ("E-006", "8d43b45-e2e-454b7b83", "A generic tube; unverified parts are drafted, flagged"),
    (
        "E-007",
        "0e070fe-e2e-542765c8",
        "Triage told to default to safety when unsure (inconclusive)",
    ),
    ("E-008", "ad2d634-e2e-5a12197c", "E-007 run again, nothing changed: two identical runs"),
    (
        "E-009",
        "412abfa-e2e-33bfeed9",
        "Triage asks for structured output as a JSON schema, not a forced tool call (Haiku 5.5)",
    ),
    (
        "E-010",
        "412abfa-e2e-7bc9d206",
        "Opus 5.5 as agent and triage, same JSON-schema method (partial: OpenRouter's in-flight "
        "credit reservation refused half the runs)",
    ),
]
EXPECTED_RUNS = 186  # 62 cases x 3 repetitions


def stat(per_rep: dict[int, list[float]]) -> dict | None:
    """Mean over every score, and the spread (max - min) of the per-repetition means."""
    if not per_rep:
        return None
    every = [v for vs in per_rep.values() for v in vs]
    means = [sum(vs) / len(vs) for vs in per_rep.values()]
    return {"mean": sum(every) / len(every), "spread": max(means) - min(means), "n": len(every)}


def summarize(rows: list[dict]) -> dict:
    by_key = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))  # key -> slice -> rep
    for row in rows:
        for key, score in row["scores"].items():
            if score is not None and key != "queue_note":
                by_key[key][row["slice"]][row["rep"]].append(score)
                by_key[key]["all"][row["rep"]].append(score)
    # Flags and slice stats live under separate keys: one of the slices is itself named "safety".
    return {
        key: {"is_safety": key in SAFETY_KEYS, "is_judge": key in JUDGES,
              "slices": {name: stat(reps) for name, reps in slices.items()}}
        for key, slices in sorted(by_key.items())
    }  # fmt: skip


def confusion(rows: list[dict]) -> dict:
    """Row-level expected (Justin's label) against predicted severity, with the cases in each
    cell and in how many repetitions they landed there."""
    cells = defaultdict(lambda: defaultdict(int))
    for row in rows:
        for rid, expected in row["expected"].items():
            predicted = row["predicted"].get(rid)
            if predicted is not None:
                cells[(expected, predicted)][f"{row['case']}:{rid}"] += 1
    return {
        "labels": SEVERITIES,
        "cells": [
            {"expected": e, "predicted": p, "count": sum(c.values()),
             "cases": [{"case": k.split(":")[0], "row": k.split(":")[1], "runs": n}
                       for k, n in sorted(c.items())]}
            for (e, p), c in sorted(cells.items())
        ],
    }  # fmt: skip


def safety_misses(rows: list[dict]) -> list[dict]:
    by_case = defaultdict(lambda: defaultdict(int))
    reps = defaultdict(int)
    for row in rows:
        reps[row["case"]] += 1
        for key in SAFETY_KEYS:
            if row["scores"].get(key) == 0:
                by_case[row["case"]][key] += 1
    return [{"case": case, "reps": reps[case], "failed": dict(keys)}
            for case, keys in sorted(by_case.items())]  # fmt: skip


def commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                              text=True, check=True).stdout.strip()  # fmt: skip
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main() -> int:
    load_dotenv(find_dotenv(usecwd=True))
    client, experiments = Client(), []
    for exp_id, project, change in EXPERIMENTS:
        print(f"{exp_id}: re-scoring {project} ...", flush=True)
        rows = rescore(client, project)
        meta = (client.read_project(project_name=project).extra or {}).get("metadata", {})
        experiments.append({
            "id": exp_id, "project": project, "change": change, "runs": len(rows),
            # A run with many missing runs has repetitions of different sizes, so its spread
            # means nothing; the page shows its means without one.
            "partial": len(rows) < 0.8 * EXPECTED_RUNS,
            "agent_model": meta.get("agent_model"),
            "structured_method": meta.get("triage_structured_method") or "default",
            # The judge rubric the experiment was scored with: v2 until E-008, v3 after (D-042).
            "rubric": f"v{(meta.get('rubric_versions') or {}).get('explanation_quality', 2)}",
            "evaluators": summarize(rows), "confusion": confusion(rows),
            "safety_misses": safety_misses(rows),
        })  # fmt: skip
    snapshot = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "commit": commit(), "slices": SLICES, "severities": SEVERITIES,
        "note": "Every experiment re-scored on the current labels; judge scores as recorded "
                "(each experiment's judge rubric is shown: judge columns are not comparable "
                "across rubric versions).",
        "experiments": experiments,
    }  # fmt: skip
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(snapshot, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(experiments)} experiments)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
