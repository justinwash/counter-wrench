"""The bridge from graph runs to evaluators: a mapping bug here would quietly score every real
run wrong, so it's tested on real graph runs (scripted models, real database)."""

from test_draft import DRAFT_ARGS, HIGHTOWER, run, triage_ok

from evals.build_output import build_run_output
from evals.evaluators import load_catalog
from evals.evaluators.draft import line_coherence, parts_all_compatible, prices_match_catalog
from evals.evaluators.trajectory import compat_checked_before_draft, no_write_without_review
from tests.test_evaluators import ref


def test_drafted_run_maps_to_what_was_saved(seeded_db):
    state, _ = run(
        seeded_db,
        {"r1": [triage_ok(agrees_with_suspected_area=False, likely_causes=["Worn cassette"],
                          disagreement_reason="New chain on a worn cassette.")]},
        [[("find_compatible_parts", {"bike_id": HIGHTOWER, "category": "cassette"})],
         [("draft_work_order", {**DRAFT_ARGS, "severity": "cosmetic"})]],
        source="eval",
    )  # fmt: skip
    out = build_run_output(state, seeded_db)

    assert out.bike_id == HIGHTOWER and out.outcome == "ready_to_draft"
    a = out.assessments["r1"]
    assert (a.severity, a.agrees, a.likely_causes) == ("needs_service", False, ["Worn cassette"])
    assert a.disagreement_reason == "New chain on a worn cassette."
    assert out.row_chunks["r1"] and out.row_chunks["r1"][0].content
    assert [c.tool for c in out.tool_calls] == ["find_compatible_parts", "draft_work_order"]
    assert out.tool_calls[0].args["category"] == "cassette"

    d = out.draft
    assert d.work_order_id == state["work_order_id"] and d.status == "awaiting_review"
    assert d.severity == "needs_service"  # what was saved (code overrode the model's "cosmetic")
    assert d.labor_codes() == ["CASSETTE-INSTALL"]
    assert [line.part_id for line in d.part_lines()] == ["sram-pg-1230-11-50"]
    assert d.stored_intake["bike_id"] == HIGHTOWER


def test_real_run_scores_clean_on_the_checks_it_should_pass(seeded_db):
    state, _ = run(
        seeded_db,
        {"r1": [triage_ok()]},
        [[("find_compatible_parts", {"bike_id": HIGHTOWER, "category": "cassette"})],
         [("draft_work_order", DRAFT_ARGS)]],
    )  # fmt: skip
    out, ctx = build_run_output(state, seeded_db), load_catalog()
    for evaluator in (parts_all_compatible, prices_match_catalog, line_coherence,
                      compat_checked_before_draft, no_write_without_review):  # fmt: skip
        assert evaluator(out, ref(), ctx).score == 1.0, evaluator.__name__


def test_run_that_stops_for_answers_has_no_draft(seeded_db):
    question = triage_ok(question_for_customer="Which gears skip?")
    state, _ = run(seeded_db, {"r1": [question]}, [])
    out = build_run_output(state, seeded_db)
    assert out.outcome == "needs_answers" and out.draft is None
    assert out.questions == {"r1": "Which gears skip?"}
    assert out.assessments["r1"].question == "Which gears skip?"
