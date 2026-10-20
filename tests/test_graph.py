"""Graph logic with a scripted fake model: every path, no network."""

import uuid
from contextlib import nullcontext

import pytest
from fakes import FakeTriage
from langgraph.checkpoint.memory import InMemorySaver

from counterwrench.agent.graph import build_graph
from counterwrench.agent.nodes import Deps
from counterwrench.models import IntakeForm
from counterwrench.rag.embed import FakeEmbedder

SLASH = "trek-slash-9-8-xt-gen-6-2024"


def assessment(row_id="r1", **overrides):
    return {
        "row_id": row_id,
        "severity": "needs_service",
        "likely_causes": ["Worn cassette"],
        "agrees_with_suspected_area": True,
        **overrides,
    }


def row(row_id="r1", complaint="skipping", area="chain", note=None):
    return {"row_id": row_id, "complaint": complaint, "suspected_area": area, "note": note}


def run(db, scripts, **intake):
    fake = FakeTriage(scripts)
    deps = Deps(connect=lambda: nullcontext(db), embedder=FakeEmbedder(), triage_model=lambda: fake)
    form = IntakeForm.model_validate({"bike_id": SLASH, "rows": [row()], **intake})
    # These tests cover triage and routing, so stop before drafting (tested in test_draft.py).
    graph = build_graph(deps, checkpointer=InMemorySaver(), interrupt_before=["draft"])
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    return graph.invoke({"intake": form}, config=config), fake


def test_each_row_is_triaged_in_its_own_branch(seeded_db):
    result, fake = run(
        seeded_db,
        {"r1": [assessment("r1")], "r2": [assessment("r2", severity="needs_adjustment")]},
        rows=[row("r1"), row("r2", "brake_rub", "rotor")],
    )
    assert set(result["assessments"]) == {"r1", "r2"}
    assert set(fake.calls) == {"r1", "r2"}  # each row got its own model call
    assert result["outcome"] == "ready_to_draft" and result["triage_retries"] == 0


def test_each_branch_gets_only_its_own_chunks(seeded_db):
    result, fake = run(
        seeded_db,
        {"r1": [assessment("r1")], "r2": [assessment("r2")]},
        rows=[row("r1"), row("r2", "brake_rub", "rotor")],
    )
    r1_prompt = fake.calls["r1"][0][1].content
    r1_chunks = {h.chunk_id for h in result["row_chunks"]["r1"]}
    r2_only = {h.chunk_id for h in result["row_chunks"]["r2"]} - r1_chunks
    assert all(f'chunk_id="{c}"' in r1_prompt for c in r1_chunks)
    assert not any(f'chunk_id="{c}"' in r1_prompt for c in r2_only)


def test_every_row_sees_the_never_release_list(seeded_db):
    result, fake = run(
        seeded_db,
        {"r1": [assessment("r1")], "r2": [assessment("r2")]},
        rows=[row("r1"), row("r2", "brake_rub", "rotor")],
    )
    for row_id in ("r1", "r2"):
        ids = [h.chunk_id for h in result["row_chunks"][row_id]]
        assert ids.count("policy-safety#what-we-never-release") == 1
        assert 'chunk_id="policy-safety#what-we-never-release"' in fake.calls[row_id][0][1].content


def test_invalid_output_is_retried_with_the_error_fed_back(seeded_db):
    bad = assessment(agrees_with_suspected_area=False)  # disagreeing without a reason
    result, fake = run(seeded_db, {"r1": [bad, assessment()]})
    assert "r1" in result["assessments"] and result["triage_retries"] == 1
    retry_messages = fake.calls["r1"][1]
    assert "invalid" in retry_messages[-1].content


def test_invented_labor_code_is_caught_and_retried(seeded_db):
    result, fake = run(
        seeded_db,
        {
            "r1": [
                assessment(suggested_labor=["MAGIC-FIX"]),
                assessment(suggested_labor=["CASSETTE-INSTALL"]),
            ]
        },
    )
    assert result["assessments"]["r1"].suggested_labor == ["CASSETTE-INSTALL"]
    assert "not on the service menu" in fake.calls["r1"][1][-1].content


def test_citations_must_come_from_the_retrieved_chunks(seeded_db):
    result, fake = run(seeded_db, {"r1": [assessment(citations=["made-up#chunk"]), assessment()]})
    assert result["triage_retries"] == 1
    assert "Citations not among" in fake.calls["r1"][1][-1].content


def test_still_invalid_after_retry_goes_to_mechanic(seeded_db):
    result, _ = run(seeded_db, {"r1": ["garbage", "more garbage"]})
    assert result["failed_rows"] == {"r1": "more garbage"}
    assert result["outcome"] == "needs_mechanic" and "r1" not in result.get("assessments", {})


def test_row_questions_go_on_to_the_draft(seeded_db):
    result, _ = run(seeded_db, {"r1": [assessment(question_for_customer="Which gear?")]})
    assert result["outcome"] == "ready_to_draft"
    assert result["questions"] == {"r1": "Which gear?"}


def test_safety_critical_escalates_even_with_open_questions(seeded_db):
    result, _ = run(
        seeded_db,
        {"r1": [assessment("r1", severity="safety_critical")],
         "r2": [assessment("r2", question_for_customer="Since when?")]},
        rows=[row("r1"), row("r2", "brake_rub", "rotor")],
    )  # fmt: skip
    assert result["outcome"] == "escalated" and result["escalated"] is True
    assert result["escalation_message"].startswith("DO NOT RIDE")
    assert result["questions"] == {"r2": "Since when?"}  # still returned for the counter


def test_ambiguous_freetext_bike_raises_a_question_in_code(seeded_db):
    result, _ = run(
        seeded_db,
        {"r1": [assessment()]},
        bike_id=None,
        bike_freetext="Trek Marlin 7, not sure what year",
    )
    assert result["bike"] is None
    assert result["outcome"] == "needs_answers"
    assert "2023" in result["questions"]["bike"] and "2025" in result["questions"]["bike"]


@pytest.mark.parametrize("bike_id", ["no-such-bike"])
def test_unknown_catalog_id_still_triages(seeded_db, bike_id):
    result, _ = run(seeded_db, {"r1": [assessment()]}, bike_id=bike_id)
    assert result["bike"] is None and "not found" in result["bike_note"]
    assert "r1" in result["assessments"]


def test_unsure_staff_pick_means_agreement_does_not_apply(seeded_db):
    # Even if the model "disagrees" with an unsure pick, code sets agreement to n/a.
    result, _ = run(
        seeded_db,
        {"r1": [assessment(agrees_with_suspected_area=False, disagreement_reason="It's the pads")]},
        rows=[row("r1", "squeak", "unsure", "grinding when braking")],
    )
    a = result["assessments"]["r1"]
    assert a.agrees_with_suspected_area is None and a.disagreement_reason is None


def run_with_flags(db, scripts, flags):
    fake = FakeTriage(scripts)
    deps = Deps(connect=lambda: nullcontext(db), embedder=FakeEmbedder(), triage_model=lambda: fake)
    form = IntakeForm.model_validate({"bike_id": SLASH, "rows": [row()]})
    graph = build_graph(deps, checkpointer=InMemorySaver(), interrupt_before=["draft"])
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    return graph.invoke({"intake": form, "guardrail_flags": flags}, config=config)


def test_instruction_override_escalates_in_code(seeded_db):
    # Shop policy: an attempt to override the assistant is a safety hazard until inspected,
    # whatever severity the model chose.
    result = run_with_flags(seeded_db, {"r1": [assessment()]}, ["instruction_override"])
    assert result["assessments"]["r1"].severity == "safety_critical"
    assert result["outcome"] == "escalated"
    assert "override the assistant" in result["escalation_message"]


@pytest.mark.parametrize("flags", [["role_tag"], ["approval_pressure"], ["out_of_scope"], []])
def test_other_flags_leave_severity_to_triage(seeded_db, flags):
    result = run_with_flags(seeded_db, {"r1": [assessment()]}, flags)
    assert result["assessments"]["r1"].severity == "needs_service"
    assert result["outcome"] == "ready_to_draft"
