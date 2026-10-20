"""Build the judge-calibration set from one experiment's judged runs (step 18).

    uv run python -m evals.calibration.build_set <experiment>

Per judge, 20 items: 10 the judge passed and 10 it failed, at most one per case, spread across
slices, so agreement is measured on both kinds of verdict. Each group of 10 splits 6 dev / 4
held-out: the rubric may be tuned on dev only, and the final numbers come from held-out.
The judge's verdict is stored here but never shown on the labeling page (Justin labels blind).
"""

from __future__ import annotations

import json
import random
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from langsmith import Client

from evals.datasets.schema import load_e2e
from evals.datasets.upload import E2E_DATASET, example_uuid

SET_FILE = Path(__file__).parent / "set.json"
JUDGES = ("diagnosis_reasonable", "explanation_quality")
PER_VERDICT, DEV = 10, 6
SEED = 18


def feedback(client: Client, run_id) -> dict:
    return {f.key: (f.score, f.comment) for f in client.list_feedback(run_ids=[run_id])}


def candidates(client: Client, experiment: str) -> dict[tuple[str, str], list[dict]]:
    """(judge, "pass"|"fail") -> one candidate item per case."""
    examples = {str(example_uuid(E2E_DATASET, e.id)): e for e in load_e2e()}
    runs = [r for r in client.list_runs(project_name=experiment, is_root=True) if not r.error]
    with ThreadPoolExecutor(max_workers=8) as pool:
        fetched = pool.map(lambda r: feedback(client, r.id), runs)
        fb = dict(zip([str(r.id) for r in runs], fetched, strict=True))
    groups: dict[tuple[str, str], dict[str, dict]] = defaultdict(dict)
    for run in sorted(runs, key=lambda r: str(r.id)):
        example = examples[str(run.reference_example_id)]
        output = run.outputs["run"]
        for judge in JUDGES:
            score, comment = fb[str(run.id)].get(judge, (None, None))
            if score is None:
                continue
            # Diagnosis is judged per row; keep single-row cases so one verdict is one item.
            if judge == "diagnosis_reasonable" and len(example.rows) != 1:
                continue
            verdict = "pass" if score == 1.0 else "fail"
            groups[(judge, verdict)].setdefault(example.id, {
                "judge": judge, "case": example.id, "slice": example.slice,
                "run_id": str(run.id), "judge_verdict": verdict, "judge_comment": comment,
                "intake": example.intake.model_dump(mode="json", exclude_none=True),
                "judge_notes": example.judge_notes, "output": output,
            })  # fmt: skip
    return {k: list(v.values()) for k, v in groups.items()}


def spread_by_slice(items: list[dict], n: int, rng: random.Random) -> list[dict]:
    by_slice = defaultdict(list)
    for item in items:
        by_slice[item["slice"]].append(item)
    for group in by_slice.values():
        rng.shuffle(group)
    order = sorted(by_slice)
    picked = []
    while len(picked) < n and any(by_slice.values()):
        for name in order:
            if by_slice[name] and len(picked) < n:
                picked.append(by_slice[name].pop())
    return picked


def build(client: Client, experiment: str) -> list[dict]:
    rng = random.Random(SEED)
    pools = candidates(client, experiment)
    items = []
    for judge in JUDGES:
        for verdict in ("pass", "fail"):
            chosen = spread_by_slice(pools.get((judge, verdict), []), PER_VERDICT, rng)
            if len(chosen) < PER_VERDICT:
                print(
                    f"note: only {len(chosen)} {judge} {verdict} items available", file=sys.stderr
                )
            for i, item in enumerate(chosen):
                item["split"] = "dev" if i < DEV else "heldout"
                items.append(item)
    rng.shuffle(items)  # so the labeling page doesn't group passes and fails
    for i, item in enumerate(items, start=1):
        item["id"] = f"cal-{i:02d}"
    return items


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python -m evals.calibration.build_set <experiment>")
        return 2
    load_dotenv(find_dotenv(usecwd=True))
    items = build(Client(), sys.argv[1])
    payload = {"experiment": sys.argv[1], "seed": SEED, "items": items}
    SET_FILE.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", "utf-8")
    counts = defaultdict(int)
    for item in items:
        counts[(item["judge"], item["judge_verdict"], item["split"])] += 1
    print(f"{len(items)} items -> {SET_FILE}")
    for key, n in sorted(counts.items()):
        print("  ", *key, n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
