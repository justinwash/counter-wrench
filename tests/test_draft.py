"""Drafting loop and human review, with scripted fake models."""

import uuid
from contextlib import nullcontext

import pytest
from fakes import FakeAgent, FakeTriage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from counterwrench.agent.graph import build_graph
from counterwrench.agent.nodes import MAX_DRAFT_STEPS, Deps
from counterwrench.agent.review import ReviewDecision, ReviewError, apply_review
from counterwrench.models import IntakeForm
from counterwrench.rag.embed import FakeEmbedder

HIGHTOWER = "santa-cruz-hightower-r-carbon-c-2024"
SLASH = "trek-slash-9-8-xt-gen-6-2024"


def triage_ok(row_id="r1", **overrides):
    return {
        "row_id": row_id,
        "severity": "needs_service",
        "likely_causes": ["Worn cassette"],
        "agrees_with_suspected_area": True,
        "suggested_labor": ["CASSETTE-INSTALL"],
        "suggested_part_categories": ["cassette"],
        **overrides,
    }


DRAFT_ARGS = {
    "bike_id": HIGHTOWER,
    "severity": "needs_service",
    "labor_lines": [{"code": "CASSETTE-INSTALL"}],
    "part_lines": [{"part_id": "sram-pg-1230-11-50"}],
    "customer_explanation": "Your cassette is worn; a new one stops the skipping.",
}


def run(db, triage_scripts, agent_turns, bike_id=HIGHTOWER, resume=None):
    agent = FakeAgent(agent_turns)
    deps = Deps(
        connect=lambda: nullcontext(db),
        embedder=FakeEmbedder(),
        triage_model=lambda: FakeTriage(triage_scripts),
        agent_model=lambda: agent,
    )
    graph = build_graph(deps, checkpointer=InMemorySaver())
    run_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": run_id}}
    intake = IntakeForm.model_validate(
        {"bike_id": bike_id, "rows": [{"row_id": "r1", "complaint": "skipping",
                                       "suspected_area": "chain"}]}
    )  # fmt: skip
    result = graph.invoke({"intake": intake, "run_id": run_id}, config=config)
    if resume is not None:
        result = graph.invoke(Command(resume=resume), config=config)
    return result, agent


def order(db, order_id):
    return db.execute(
        "SELECT status, bike_id, severity, priority, langsmith_run_id, reviewed_by, "
        "review_notes FROM work_orders WHERE id = %s",
        (order_id,),
    ).fetchone()


# --- Drafting ----------------------------------------------------------------------------------


def test_draft_is_saved_through_tool_calls_and_pauses_for_review(seeded_db):
    result, agent = run(
        seeded_db,
        {"r1": [triage_ok()]},
        [[("find_compatible_parts", {"bike_id": HIGHTOWER, "category": "cassette"})],
         [("draft_work_order", DRAFT_ARGS)]],
    )  # fmt: skip
    assert result["__interrupt__"][0].value["work_order_id"] == result["work_order_id"]
    assert [c["tool"] for c in result["tool_calls"]] == [
        "find_compatible_parts",
        "draft_work_order",
    ]
    assert order(seeded_db, result["work_order_id"])[0] == "awaiting_review"
    assert set(agent.bound_tools) == {
        "find_compatible_parts", "get_labor_item", "search_labor_menu", "draft_work_order"
    }  # fmt: skip


def test_saved_order_links_to_its_trace(seeded_db):
    result, _ = run(seeded_db, {"r1": [triage_ok()]}, [[("draft_work_order", DRAFT_ARGS)]])
    assert str(order(seeded_db, result["work_order_id"])[4]) == result["run_id"]


def test_rejected_draft_is_fixed_and_resubmitted(seeded_db):
    bad = {**DRAFT_ARGS, "part_lines": [{"part_id": "shimano-cs-m7100-10-51"}]}  # won't fit
    result, _ = run(
        seeded_db,
        {"r1": [triage_ok()]},
        [[("draft_work_order", bad)], [("draft_work_order", DRAFT_ARGS)]],
    )
    assert result["work_order_id"] is not None
    assert [c["tool"] for c in result["tool_calls"]] == ["draft_work_order", "draft_work_order"]
    assert seeded_db.execute("SELECT count(*) FROM work_orders").fetchone() == (1,)


def test_model_cannot_choose_the_bike_or_lower_the_severity(seeded_db):
    sneaky = {**DRAFT_ARGS, "bike_id": SLASH, "severity": "cosmetic"}
    result, _ = run(
        seeded_db,
        {"r1": [triage_ok(severity="safety_critical")]},
        [[("draft_work_order", {**sneaky, "part_lines": []})]],
    )
    status, bike_id, severity, priority, *_ = order(seeded_db, result["work_order_id"])
    assert (bike_id, severity, priority) == (HIGHTOWER, "safety_critical", True)


def test_no_saved_draft_within_the_step_limit_goes_to_a_mechanic(seeded_db):
    stuck = [[("search_labor_menu", {"query": "cassette"})]] * (MAX_DRAFT_STEPS + 2)
    result, agent = run(seeded_db, {"r1": [triage_ok()]}, stuck)
    assert agent.calls == MAX_DRAFT_STEPS
    assert result["outcome"] == "needs_mechanic" and result["work_order_id"] is None
    assert "__interrupt__" not in result


def test_model_stopping_without_drafting_goes_to_a_mechanic(seeded_db):
    result, _ = run(seeded_db, {"r1": [triage_ok()]}, ["I think we're done."])
    assert result["outcome"] == "needs_mechanic" and result["draft_error"]


def test_bad_tool_arguments_come_back_as_text(seeded_db):
    result, _ = run(
        seeded_db,
        {"r1": [triage_ok()]},
        [[("draft_work_order", {"severity": "needs_service"})],  # missing explanation
         [("draft_work_order", DRAFT_ARGS)]],
    )  # fmt: skip
    assert result["work_order_id"] is not None


def test_needs_answers_never_drafts(seeded_db):
    result, agent = run(
        seeded_db,
        {"r1": [triage_ok(question_for_customer="Which gears skip?")]},
        [[("draft_work_order", DRAFT_ARGS)]],
    )
    assert agent.calls == 0 and result["outcome"] == "needs_answers"
    assert seeded_db.execute("SELECT count(*) FROM work_orders").fetchone() == (0,)


# --- Human review ---------------------------------------------------------------------------------


def test_resume_with_approval_records_the_reviewer(seeded_db):
    result, _ = run(
        seeded_db,
        {"r1": [triage_ok()]},
        [[("draft_work_order", DRAFT_ARGS)]],
        resume={"decision": "approve", "reviewer": "justin"},
    )
    status, *_, reviewed_by, _ = order(seeded_db, result["work_order_id"])
    assert (status, reviewed_by) == ("approved", "justin")
    assert result["review"]["status"] == "approved"


def test_resume_with_rejection_keeps_the_reason(seeded_db):
    result, _ = run(
        seeded_db,
        {"r1": [triage_ok()]},
        [[("draft_work_order", DRAFT_ARGS)]],
        resume={"decision": "reject", "reviewer": "justin", "notes": "Chain is worn too."},
    )
    assert order(seeded_db, result["work_order_id"])[0] == "rejected"
    assert order(seeded_db, result["work_order_id"])[6] == "Chain is worn too."


def test_rejection_without_notes_is_refused():
    with pytest.raises(ValueError):
        ReviewDecision(decision="reject", reviewer="justin")


def test_review_only_applies_to_orders_awaiting_review(seeded_db):
    result, _ = run(
        seeded_db,
        {"r1": [triage_ok()]},
        [[("draft_work_order", DRAFT_ARGS)]],
        resume={"decision": "approve", "reviewer": "justin"},
    )
    with pytest.raises(ReviewError):
        apply_review(
            seeded_db, result["work_order_id"], ReviewDecision(decision="approve", reviewer="x")
        )
