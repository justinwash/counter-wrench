"""Run the graph on an intake file: python -m counterwrench.agent.run data/samples/<file>.json"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

from counterwrench.agent.graph import build_graph, default_deps
from counterwrench.config import load_config
from counterwrench.models import IntakeForm
from counterwrench.tracing import run_metadata, trace_url


def print_result(result: dict) -> None:
    print(f"Bike: {result.get('bike_note')}")
    for row_id, a in result.get("assessments", {}).items():
        print(f"\n[{row_id}] {a.severity.upper()}")
        print(f"  likely causes: {'; '.join(a.likely_causes)}")
        if a.agrees_with_suspected_area is None:
            stance = "n/a (staff unsure)"
        elif a.agrees_with_suspected_area:
            stance = "agrees"
        else:
            stance = f"DISAGREES: {a.disagreement_reason}"
        print(f"  staff's suspected area: {stance}")
        if a.question_for_customer:
            print(f"  question: {a.question_for_customer}")
        parts = [str(c) for c in a.suggested_part_categories]
        print(f"  labor: {a.suggested_labor or '-'}  parts: {parts or '-'}")
        print(f"  cited: {a.citations or '-'}")
    for row_id, error in result.get("failed_rows", {}).items():
        print(f"\n[{row_id}] COULDN'T ASSESS (mechanic review): {error}")
    print(f"\nOutcome: {result['outcome']}  (triage retries: {result.get('triage_retries', 0)})")
    if result.get("escalation_message"):
        print(result["escalation_message"])
    for key, question in result.get("questions", {}).items():
        print(f"  Ask [{key}]: {question}")


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m counterwrench.agent.run")
    parser.add_argument("intake", type=Path)
    args = parser.parse_args()

    config = load_config()
    intake = IntakeForm.model_validate_json(args.intake.read_text("utf-8"))
    run_id = uuid.uuid4()
    graph = build_graph(default_deps(config))
    result = graph.invoke(
        {"intake": intake},
        config={
            "run_id": run_id,
            "run_name": "counterwrench",
            "tags": ["cli", args.intake.stem],
            "metadata": run_metadata(config, intake_file=args.intake.name),
        },
    )
    print_result(result)
    url = trace_url(run_id)
    if url:
        print(f"\nTrace: {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
