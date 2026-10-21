"""Re-run the judges, with the current rubrics, on the calibration items (step 18).

    uv run python -m evals.calibration.rejudge

The judges see exactly what the original judges saw (the same agent output, intake and case
notes, all stored in set.json), so only the rubric changes. Writes verdicts_v<N>.json for
`agreement.py --verdicts`.
"""

from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor

from counterwrench.config import get_chat_model
from counterwrench.models import IntakeForm
from evals.calibration.agreement import SET_FILE
from evals.datasets.schema import load_e2e
from evals.evaluators import Reference, load_catalog
from evals.evaluators.judge import load_rubric, make_judges
from evals.run_output import RunOutput


def reference(item: dict, examples: dict) -> Reference:
    example = examples[item["case"]]
    return Reference(
        intake=IntakeForm.model_validate(item["intake"]),  # as the original judge saw it
        rows=example.rows,
        escalation_required=example.escalation_required,
        bike_question_expected=example.bike_question_expected,
        order_expected=example.order_expected,
        judge_notes=item["judge_notes"],
    )


def main() -> int:
    items = json.loads(SET_FILE.read_text("utf-8"))["items"]
    examples = {e.id: e for e in load_e2e()}
    judges = {j.__name__: j for j in make_judges(get_chat_model("judge"))}
    ctx = load_catalog()

    def judge(item: dict) -> tuple[str, dict]:
        out = RunOutput.model_validate(item["output"])
        score = judges[item["judge"]](out, reference(item, examples), ctx)
        verdict = "pass" if score.score == 1.0 else "fail"
        return item["id"], {"verdict": verdict, "comment": score.comment}

    with ThreadPoolExecutor(max_workers=6) as pool:
        verdicts = dict(pool.map(judge, items))
    versions = {n: load_rubric(n).version for n in ("diagnosis_reasonable", "explanation_quality")}
    path = SET_FILE.parent / f"verdicts_v{max(versions.values())}.json"
    payload = {"rubric_versions": versions, "verdicts": verdicts}
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", "utf-8")
    print(f"{len(verdicts)} verdicts -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
