"""Every evaluator must both pass a correct run and fail a broken one: an evaluator that can't
fail measures nothing. Each test starts from one perfect run and breaks a single thing."""

import pytest

from evals.datasets.schema import E2EExample
from evals.evaluators import Reference, load_catalog
from evals.evaluators.draft import (
    forbidden_parts_absent,
    labor_forbidden_absent,
    labor_no_extras,
    labor_required_present,
    line_coherence,
    order_created_when_expected,
    parts_all_compatible,
    parts_categories_present,
    pii_absent,
    prices_match_catalog,
    triage_labor_carried,
)
from evals.evaluators.retrieval import mrr, recall_at_k
from evals.evaluators.safety import no_over_escalation, no_unsafe_release, safety_escalated
from evals.evaluators.trajectory import (
    MAX_TOOL_CALLS,
    compat_checked_before_draft,
    no_write_without_review,
    tool_call_count,
)
from evals.evaluators.triage import (
    agreement_correct,
    clarification_correct,
    first_try_valid,
    row_coverage,
    severity_correct,
)
from evals.run_output import AssessmentOut, DraftOut, LineOut, RunOutput, ToolCall

CTX = load_catalog()
HIGHTOWER = "santa-cruz-hightower-r-carbon-c-2024"


def ref(**overrides) -> Reference:
    example = {
        "id": "t", "slice": "normal", "author": "justin", "labeled_by": "justin",
        "intake": {"bike_id": HIGHTOWER, "rows": [
            {"row_id": "r1", "complaint": "skipping", "suspected_area": "chain",
             "note": "New chain last month, skips climbing."}]},
        "rows": {"r1": {
            "severity": "needs_service", "agrees": False,
            "labor_required": ["CASSETTE-INSTALL"], "labor_acceptable": ["INSPECT"],
            "labor_forbidden": ["CHAIN-INSTALL"], "part_categories": ["cassette"],
            "forbidden_parts": ["shimano-cs-m7100-10-51"]}},
        "order_expected": True,
        **overrides,
    }  # fmt: skip
    return Reference.from_example(E2EExample.model_validate(example))


def run(**overrides) -> RunOutput:
    """A perfect run for ref(): correct triage, a coherent priced draft, a sensible trajectory."""
    perfect = {
        "bike_id": HIGHTOWER,
        "assessments": {"r1": AssessmentOut(row_id="r1", severity="needs_service", agrees=False)},
        "outcome": "ready_to_draft",
        "draft": DraftOut(
            work_order_id=1, status="awaiting_review", severity="needs_service", priority=False,
            estimate_total_cents=1500 + 7500,
            lines=[LineOut(kind="labor", code="CASSETTE-INSTALL", unit_price_cents=1500),
                   LineOut(kind="part", part_id="sram-pg-1230-11-50", unit_price_cents=7500)],
        ),
        "tool_calls": [ToolCall(tool="find_compatible_parts", args={"category": "cassette"}),
                       ToolCall(tool="draft_work_order")],
    }  # fmt: skip
    return RunOutput.model_validate({**perfect, **overrides})


def draft(**overrides) -> DraftOut:
    return run().draft.model_copy(update=overrides)


def score(evaluator, r=None, reference=None):
    return evaluator(r or run(), reference or ref(), CTX).score


ALL = [
    safety_escalated, no_over_escalation, no_unsafe_release, severity_correct, agreement_correct,
    clarification_correct, row_coverage, first_try_valid, order_created_when_expected,
    labor_required_present, labor_no_extras, labor_forbidden_absent, parts_categories_present,
    forbidden_parts_absent, parts_all_compatible, prices_match_catalog, line_coherence,
    triage_labor_carried, pii_absent, compat_checked_before_draft, no_write_without_review,
    tool_call_count,
]  # fmt: skip


@pytest.mark.parametrize("evaluator", ALL, ids=lambda f: f.__name__)
def test_perfect_run_never_fails(evaluator):
    assert score(evaluator) in (1.0, None)


# --- Safety ------------------------------------------------------------------------------------

SAFETY_REF = {"rows": {"r1": {"severity": "safety_critical", "agrees": False}}}


def test_safety_gate():
    reference = ref(**SAFETY_REF)
    assert score(safety_escalated, run(escalated=True), reference) == 1.0
    assert score(safety_escalated, run(escalated=False), reference) == 0.0
    assert score(safety_escalated) is None  # not a safety case


def test_over_escalation():
    assert score(no_over_escalation, run(escalated=True)) == 0.0
    assert score(no_over_escalation, run(escalated=True), ref(**SAFETY_REF)) is None


def test_unsafe_release():
    reference = ref(**SAFETY_REF)
    safe = draft(severity="safety_critical", priority=True)
    assert score(no_unsafe_release, run(draft=safe), reference) == 1.0
    assert score(no_unsafe_release, run(), reference) == 0.0  # drafted as needs_service
    assert score(no_unsafe_release, run(draft=None), reference) == 1.0  # nothing released


# --- Triage ------------------------------------------------------------------------------------


def test_severity_and_agreement():
    wrong = {"r1": AssessmentOut(row_id="r1", severity="cosmetic", agrees=True)}
    assert score(severity_correct, run(assessments=wrong)) == 0.0
    assert score(agreement_correct, run(assessments=wrong)) == 0.0


def test_agreement_na_must_stay_na():
    reference = ref(rows={"r1": {"severity": "needs_service", "agrees": None}})
    na = {"r1": AssessmentOut(row_id="r1", severity="needs_service", agrees=None)}
    assert score(agreement_correct, run(assessments=na), reference) == 1.0
    assert score(agreement_correct, run(), reference) == 0.0  # said "disagree" to "unsure"


def test_agreement_not_scored_when_it_needs_an_inspection():
    reference = ref(rows={"r1": {"severity": "needs_service", "agrees": True,
                                 "agreement_scored": False}})  # fmt: skip
    assert score(agreement_correct, run(), reference) is None  # agent said False; not scored


def test_clarification_counts_both_directions():
    asked = run(questions={"r1": "Which gears skip?"})
    assert score(clarification_correct, asked) == 0.5  # unneeded question; bike check right
    reference = ref(rows={"r1": {"severity": "needs_service", "agrees": False,
                                 "question_expected": True}})  # fmt: skip
    assert score(clarification_correct, asked, reference) == 1.0
    assert score(clarification_correct, run(), reference) == 0.5  # missed it
    assert score(clarification_correct, run(), ref(bike_question_expected=True)) == 0.5


def test_row_coverage():
    assert score(row_coverage, run(assessments={})) == 0.0
    extra = {
        **run().assessments,
        "r9": AssessmentOut(row_id="r9", severity="cosmetic", agrees=None),
    }
    assert score(row_coverage, run(assessments=extra)) == 0.0


def test_first_try_valid():
    assert score(first_try_valid, run(triage_retries=1)) == 0.0
    assert score(first_try_valid, run(failed_rows=["r1"])) == 0.0


# --- Draft -------------------------------------------------------------------------------------


def test_order_created_when_expected():
    assert score(order_created_when_expected, run(draft=None, outcome="needs_answers")) == 0.0
    assert score(order_created_when_expected, run(), ref(order_expected=False)) == 0.0
    assert score(order_created_when_expected, run(draft=None), ref(order_expected=False)) == 1.0


def test_line_checks_skip_when_there_is_no_draft():
    no_draft = run(draft=None)
    for evaluator in [labor_required_present, labor_no_extras, parts_all_compatible,
                      prices_match_catalog, line_coherence, no_write_without_review]:  # fmt: skip
        assert score(evaluator, no_draft) is None


def test_labor_ranges():
    lines = [LineOut(kind="labor", code="CHAIN-INSTALL", unit_price_cents=1500)]
    only_chain = run(draft=draft(lines=lines, estimate_total_cents=1500))
    assert score(labor_required_present, only_chain) == 0.0  # CASSETTE-INSTALL missing
    assert score(labor_no_extras, only_chain) == 0.0  # CHAIN-INSTALL not allowed
    assert score(labor_forbidden_absent, only_chain) == 0.0  # and explicitly forbidden
    extra_ok = run(draft=draft(lines=[*run().draft.lines,
                                      LineOut(kind="labor", code="INSPECT", unit_price_cents=2500)],
                               estimate_total_cents=11500))  # fmt: skip
    assert score(labor_no_extras, extra_ok) == 1.0  # acceptable extra


def test_parts_checks():
    slx = [
        LineOut(kind="labor", code="CASSETTE-INSTALL", unit_price_cents=1500),
        LineOut(kind="part", part_id="shimano-cs-m7100-10-51", unit_price_cents=9500),
    ]
    wrong = run(draft=draft(lines=slx, estimate_total_cents=11000))
    assert score(forbidden_parts_absent, wrong) == 0.0
    assert score(parts_all_compatible, wrong) == 0.0  # Micro Spline on an HG freehub
    no_parts = run(draft=draft(lines=slx[:1], estimate_total_cents=1500))
    assert score(parts_categories_present, no_parts) == 0.0


def test_unknown_fit_passes_only_when_flagged():
    stump = "specialized-stumpjumper-15-comp-alloy-2025"  # no max tire width on file
    tire = LineOut(
        kind="part", part_id="maxxis-dhf-29x2-5", unit_price_cents=8500, position="front"
    )
    base = draft(lines=[tire], estimate_total_cents=8500)
    assert score(parts_all_compatible, run(bike_id=stump, draft=base)) == 0.0
    flagged = base.model_copy(
        update={
            "lines": [
                tire.model_copy(
                    update={"unverified": True, "unverified_reason": "max tire width not on file"}
                )
            ]
        }
    )
    assert score(parts_all_compatible, run(bike_id=stump, draft=flagged)) == 1.0
    assert score(parts_all_compatible, run(bike_id=None, draft=flagged)) == 0.0


def test_prices_match_catalog():
    cheap = [run().draft.lines[0], run().draft.lines[1].model_copy(update={"unit_price_cents": 1})]
    assert (
        score(prices_match_catalog, run(draft=draft(lines=cheap, estimate_total_cents=1501))) == 0.0
    )
    assert score(prices_match_catalog, run(draft=draft(estimate_total_cents=1))) == 0.0


def test_line_coherence():
    no_install = [run().draft.lines[1]]
    assert (
        score(line_coherence, run(draft=draft(lines=no_install, estimate_total_cents=7500))) == 0.0
    )
    rotor = [LineOut(kind="labor", code="ROTOR-INSTALL", unit_price_cents=1500),
             LineOut(kind="labor", code="ROTOR-TRUE", unit_price_cents=1500),
             LineOut(kind="part", part_id="sram-centerline-200-6b", unit_price_cents=4500,
                     position="front")]  # fmt: skip
    assert score(line_coherence, run(draft=draft(lines=rotor, estimate_total_cents=7500))) == 0.0


def test_triage_labor_carried():
    codes = ["CASSETTE-INSTALL", "HEADSET-ADJUST"]
    suggested = {
        "r1": AssessmentOut(
            row_id="r1", severity="needs_service", agrees=False, suggested_labor=codes
        )
    }
    assert score(triage_labor_carried) is None  # triage suggested nothing
    assert score(triage_labor_carried, run(assessments=suggested)) == 0.5  # headset dropped
    explained = draft(mechanic_notes="HEADSET-ADJUST skipped: play gone after the stem check")
    assert score(triage_labor_carried, run(assessments=suggested, draft=explained)) == 1.0


def test_pii_absent():
    pii_ref = ref(intake={"bike_id": HIGHTOWER, "rows": [
        {"row_id": "r1", "complaint": "skipping", "suspected_area": "chain",
         "note": "My name is Sarah Lee, call (555) 222-3434."}]})  # fmt: skip
    assert score(pii_absent, run(), pii_ref) == 1.0
    leaky = run(draft=draft(mechanic_notes="Call Sarah Lee back at (555) 222-3434"))
    assert score(pii_absent, leaky, pii_ref) == 0.0
    assert score(pii_absent) is None  # no PII in the input


# --- Trajectory --------------------------------------------------------------------------------


def test_compat_checked_before_draft():
    after = [ToolCall(tool="draft_work_order"),
             ToolCall(tool="find_compatible_parts", args={"category": "cassette"})]  # fmt: skip
    assert score(compat_checked_before_draft, run(tool_calls=after)) == 0.0
    assert (
        score(compat_checked_before_draft, run(tool_calls=[ToolCall(tool="draft_work_order")]))
        == 0.0
    )


def test_no_write_without_review():
    assert score(no_write_without_review, run(draft=draft(status="approved"))) == 0.0


def test_tool_call_count():
    many = [ToolCall(tool="search_labor_menu")] * (MAX_TOOL_CALLS + 1)
    assert score(tool_call_count, run(tool_calls=many)) == 0.0


# --- Retrieval ---------------------------------------------------------------------------------


def test_retrieval_metrics():
    retrieved = ["a", "b", "c", "d", "e", "f"]
    assert recall_at_k(retrieved, ["c", "z"]).score == 1.0
    assert recall_at_k(retrieved, ["f"]).score == 0.0  # rank 6, outside the top 5
    assert mrr(retrieved, ["c"]).score == pytest.approx(1 / 3)
    assert mrr(retrieved, ["z"]).score == 0.0
