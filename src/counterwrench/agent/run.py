"""Run the graph on an intake file:

    python -m counterwrench.agent.run data/samples/<file>.json [--review approve|reject]

Without --review, a saved draft stays paused awaiting mechanic review.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from counterwrench.agent.graph import build_graph, default_deps
from counterwrench.config import load_config
from counterwrench.guardrails import apply_guardrails
from counterwrench.models import IntakeForm
from counterwrench.tracing import run_metadata, trace_url


def _stance(a) -> str:
    if a.agrees_with_suspected_area is None:
        return "n/a (staff unsure)"
    if a.agrees_with_suspected_area:
        return "agrees"
    return f"DISAGREES: {a.disagreement_reason}"


def print_result(result: dict) -> None:
    print(f"Bike: {result.get('bike_note')}")
    for row_id, a in result.get("assessments", {}).items():
        print(f"\n[{row_id}] {a.severity.upper()}")
        print(f"  likely causes: {'; '.join(a.likely_causes)}")
        print(f"  staff's suspected area: {_stance(a)}")
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

    if result.get("tool_calls"):
        print(f"\nDrafting tool calls: {[c['tool'] for c in result['tool_calls']]}")
    draft = result.get("draft")
    if draft:
        print(
            f"Draft saved: work order #{draft['work_order_id']}, {draft['estimate_total']}, "
            f"status {draft['work_order_status']}"
        )
        if draft.get("unverified_parts"):
            print(f"  unverified (mechanic to confirm): {draft['unverified_parts']}")
    if result.get("draft_error"):
        print(result["draft_error"])
    review = result.get("review")
    if review:
        notes = f" ({review['notes']})" if review.get("notes") else ""
        print(f"Reviewed by {review['reviewer']}: {review['status']}{notes}")


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m counterwrench.agent.run")
    parser.add_argument("intake", type=Path)
    parser.add_argument(
        "--review",
        choices=["approve", "reject"],
        help="act as the mechanic: resume the paused draft with this decision",
    )
    parser.add_argument("--reviewer", default="cli-mechanic")
    parser.add_argument("--notes", help="review notes (required to reject)")
    args = parser.parse_args()

    config = load_config()
    # Guardrails run before the graph: LangSmith records the graph's input, so only the
    # redacted intake may go in.
    guarded = apply_guardrails(IntakeForm.model_validate_json(args.intake.read_text("utf-8")))
    intake = guarded.intake
    run_id = uuid.uuid4()
    graph = build_graph(default_deps(config), checkpointer=InMemorySaver())
    run_config = {
        "run_id": run_id,
        "run_name": "counterwrench",
        "tags": ["cli", args.intake.stem],
        "metadata": run_metadata(
            config,
            intake_file=args.intake.name,
            pii_redacted=guarded.pii_counts,
            guardrail_flags=sorted({f.kind for f in guarded.flags}),
        ),
        "configurable": {"thread_id": str(run_id)},
    }
    if guarded.pii_counts or guarded.flags:
        kinds = [f.kind for f in guarded.flags] or "none"
        print(f"Guardrails: redacted {guarded.pii_counts or 'nothing'}; flags {kinds}")
    state = {"intake": intake, "run_id": str(run_id), "guardrail_note": guarded.mechanic_note()}
    result = graph.invoke(state, config=run_config)
    paused = bool(result.get("__interrupt__"))
    if paused and args.review:
        decision = {"decision": args.review, "reviewer": args.reviewer, "notes": args.notes}
        resume_config = {**run_config, "run_id": uuid.uuid4(), "run_name": "counterwrench-review"}
        result = graph.invoke(Command(resume=decision), config=resume_config)
        paused = False

    print_result(result)
    if paused:
        print("(Paused for mechanic review; re-run with --review approve|reject to decide.)")
    url = trace_url(run_id)
    if url:
        print(f"\nTrace: {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
