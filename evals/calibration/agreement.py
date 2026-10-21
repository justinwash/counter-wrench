"""How well the LLM judges agree with Justin (step 18).

    uv run python -m evals.calibration.agreement [--verdicts verdicts_v3.json]

Reads the calibration set (set.json, with the judges' verdicts) and Justin's blind labels
(justin_labels.json: {"labels": {item id: {"verdict": "pass"|"fail", "reason": ...}}}). Per
judge and split: accuracy, TPR (the judge passes what Justin passes), TNR (the judge fails what
Justin fails) and Cohen's kappa, which discounts the agreement two graders reach by chance.
Every disagreement is listed: that's where the rubric needs work.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
SET_FILE = HERE / "set.json"
LABELS_FILE = HERE / "justin_labels.json"


def cohen_kappa(a: list[str], b: list[str]) -> float | None:
    """Agreement beyond chance between two graders over the same items; None if undefined."""
    if not a or len(a) != len(b):
        return None
    n = len(a)
    observed = sum(x == y for x, y in zip(a, b, strict=True)) / n
    labels = set(a) | set(b)
    expected = sum((a.count(k) / n) * (b.count(k) / n) for k in labels)
    return None if expected == 1 else (observed - expected) / (1 - expected)


def metrics(pairs: list[tuple[str, str]]) -> dict:
    """pairs: (justin, judge) verdicts."""
    justin, judge = [p[0] for p in pairs], [p[1] for p in pairs]
    pos = [j for h, j in pairs if h == "pass"]
    neg = [j for h, j in pairs if h == "fail"]
    return {
        "n": len(pairs),
        "accuracy": sum(h == j for h, j in pairs) / len(pairs) if pairs else None,
        "tpr": pos.count("pass") / len(pos) if pos else None,
        "tnr": neg.count("fail") / len(neg) if neg else None,
        "kappa": cohen_kappa(justin, judge),
    }


def _fmt(v) -> str:
    return "–" if v is None else f"{v:.2f}"


def main() -> int:
    args = sys.argv[1:]
    items = json.loads(SET_FILE.read_text("utf-8"))["items"]
    if "--verdicts" in args:  # re-judged with newer rubrics (rejudge.py) instead of the originals
        path = Path(args[args.index("--verdicts") + 1])
        rejudged = json.loads((path if path.exists() else HERE / path).read_text("utf-8"))
        print(f"Judge verdicts: {path.name}, rubrics {rejudged['rubric_versions']}")
        for item in items:
            item["judge_verdict"] = rejudged["verdicts"][item["id"]]["verdict"]
    labels_path = Path(args[0]) if args and not args[0].startswith("--") else LABELS_FILE
    labels = json.loads(labels_path.read_text("utf-8"))["labels"]
    missing = [i["id"] for i in items if i["id"] not in labels]
    if missing:
        print(f"{len(missing)} items not labeled yet: {', '.join(missing)}")
    print("| Judge | Split | n | Accuracy | TPR | TNR | Kappa |\n|---|---|---|---|---|---|---|")
    for judge in ("diagnosis_reasonable", "explanation_quality"):
        for split in ("dev", "heldout"):
            group = [i for i in items if i["judge"] == judge and i["split"] == split]
            pairs = [(labels[i["id"]]["verdict"], i["judge_verdict"]) for i in group
                     if i["id"] in labels]  # fmt: skip
            m = metrics(pairs)
            print(f"| {judge} | {split} | {m['n']} | {_fmt(m['accuracy'])} | {_fmt(m['tpr'])} "
                  f"| {_fmt(m['tnr'])} | {_fmt(m['kappa'])} |")  # fmt: skip
    print("\nDisagreements (dev first; tune the rubric on dev only):")
    for split in ("dev", "heldout"):
        for i in items:
            label = labels.get(i["id"])
            if i["split"] == split and label and label["verdict"] != i["judge_verdict"]:
                print(f"- [{split}] {i['id']} {i['judge']} {i['case']}: Justin {label['verdict']} "
                      f"({label.get('reason', '')}), judge {i['judge_verdict']}")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
