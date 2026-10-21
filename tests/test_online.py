"""Online evaluation: the live checks, and that scores reach the right run."""

from contextlib import nullcontext

import pytest
from fakes import FakeAgent, FakeTriage
from fastapi.testclient import TestClient
from test_api import continued, events, intake, triaged
from test_draft import DRAFT_ARGS, triage_ok
from test_evaluators import draft as draft_of
from test_evaluators import ref, run

from counterwrench.agent.nodes import Deps
from counterwrench.api.app import create_app
from counterwrench.models import IntakeForm
from counterwrench.online.scoring import OnlineScorer, judge_sample_rate, reference_for
from counterwrench.rag.embed import FakeEmbedder
from evals.evaluators import Score, load_catalog
from evals.evaluators import online as live
from evals.run_output import AssessmentOut

CTX = load_catalog()


def score(check, r=None):
    return check(r or run(), ref(), CTX).score


# --- The checks: each passes a good run and fails a bad one ------------------------------------


def critical(**over):
    rows = {"r1": AssessmentOut(row_id="r1", severity="safety_critical", agrees=True)}
    return run(assessments=rows, **{"escalated": True, **over})


def test_safety_consistent():
    assert score(live.safety_consistent) == 1.0  # nothing critical
    good = critical(draft=draft_of(severity="safety_critical", priority=True))
    assert score(live.safety_consistent, good) == 1.0
    assert score(live.safety_consistent, critical(escalated=False, draft=None)) == 0.0
    assert score(live.safety_consistent, critical(draft=draft_of(priority=False))) == 0.0
    assert score(live.safety_consistent, run(assessments={})) is None


def test_severity_matches_triage():
    assert score(live.severity_matches_triage) == 1.0  # triage and order both needs_service
    assert score(live.severity_matches_triage, run(draft=draft_of(severity="cosmetic"))) == 0.0
    assert score(live.severity_matches_triage, run(draft=None)) is None


def test_questions_resolved():
    assert score(live.questions_resolved) == 1.0
    assert score(live.questions_resolved, run(unresolved={"r1": "Does it squeal when dry?"})) == 0.0


def test_no_pii_in_output():
    assert score(live.no_pii_in_output) == 1.0
    leaky = run(draft=draft_of(mechanic_notes="Call Sarah at (555) 222-3434 or sarah@example.com"))
    assert score(live.no_pii_in_output, leaky) == 0.0


# --- The scorer ---------------------------------------------------------------------------------


def test_judges_run_on_the_configured_share_of_runs():
    calls = []
    judge = {
        "diagnosis_reasonable": lambda r, f, c: (
            calls.append(1) or Score("diagnosis_reasonable", 1.0)
        )
    }
    form = IntakeForm.model_validate(intake())
    for rate, draws, expected in [
        (1.0, [0.99], 1),
        (0.1, [0.5], 0),
        (0.1, [0.05], 1),
        (0.0, [0.0], 0),
    ]:
        calls.clear()
        scorer = OnlineScorer(lambda: nullcontext(None), post=lambda *_: None, judges=lambda: judge,
                              judge_rate=rate, rng=iter(draws).__next__)  # fmt: skip
        keys = [s.key for s in scorer.scores_for("triage", run(), form)]
        assert len(calls) == expected and ("diagnosis_reasonable" in keys) == bool(expected), rate


def test_a_failing_judge_keeps_the_other_scores():
    def broken(*_):
        raise RuntimeError("judge model unavailable")

    scorer = OnlineScorer(lambda: nullcontext(None), post=lambda *_: None,
                          judges=lambda: {"explanation_quality": broken})  # fmt: skip
    keys = [s.key for s in scorer.scores_for("draft", run(), IntakeForm.model_validate(intake()))]
    assert "prices_match_catalog" in keys and "explanation_quality" not in keys


def test_not_applicable_checks_are_not_posted():
    scorer = OnlineScorer(lambda: nullcontext(None), post=lambda *_: None)
    scores = scorer.scores_for("triage", run(draft=None), IntakeForm.model_validate(intake()))
    keys = [s.key for s in scores]
    assert "severity_matches_triage" not in keys and "first_try_valid" in keys


def test_the_reference_carries_no_answers_to_cheat_from():
    form = IntakeForm.model_validate(intake())
    reference = reference_for(form)
    assert set(reference.rows) == {"r1"} and reference.judge_notes is None


def test_judge_sample_rate_reads_the_environment_safely():
    assert judge_sample_rate({}) == 1.0
    assert judge_sample_rate({"CW_JUDGE_SAMPLE": "0.1"}) == 0.1
    assert judge_sample_rate({"CW_JUDGE_SAMPLE": "banana"}) == 1.0
    assert judge_sample_rate({"CW_JUDGE_SAMPLE": "7"}) == 1.0


# --- End to end: scores land on the right trace -------------------------------------------------


@pytest.fixture
def scored_app(seeded_db):
    posted = []

    def fixed(key):
        return lambda r, f, c: Score(key, 1.0, "ok")

    judges = {k: fixed(k) for k in ("diagnosis_reasonable", "explanation_quality")}
    scorer = OnlineScorer(
        lambda: nullcontext(seeded_db), post=lambda rid, s: posted.append((rid, s)),
        judges=lambda: judges, background=False,
    )  # fmt: skip

    def make(triage_scripts, turns=()):
        triage, agent = FakeTriage(triage_scripts), FakeAgent(list(turns))
        deps = Deps(connect=lambda: nullcontext(seeded_db), embedder=FakeEmbedder(),
                    triage_model=lambda: triage, agent_model=lambda: agent)  # fmt: skip
        return TestClient(create_app(deps=deps, online=scorer))

    return make, posted, seeded_db


def test_triage_scores_go_to_the_triage_run_and_draft_scores_to_the_drafting_run(scored_app):
    make, posted, db = scored_app
    api = make({"r1": [triage_ok()]}, [[("draft_work_order", DRAFT_ARGS)]])
    intake_id = triaged(api)["done"]["intake_id"]
    assert [rid for rid, _ in posted] == [intake_id]
    triage_keys = {s.key for s in posted[0][1]}
    assert {
        "first_try_valid",
        "row_coverage",
        "safety_consistent",
        "diagnosis_reasonable",
    } <= triage_keys
    assert "parts_all_compatible" not in triage_keys  # nothing drafted yet

    order_id = dict(continued(api, intake_id))["done"]["work_order_id"]
    draft_run = str(
        db.execute("SELECT draft_run_id FROM work_orders WHERE id = %s", (order_id,)).fetchone()[0]
    )
    assert [rid for rid, _ in posted] == [intake_id, draft_run]
    draft_scores = {s.key: s.score for s in posted[1][1]}
    assert (
        draft_scores["parts_all_compatible"] == 1.0 and draft_scores["prices_match_catalog"] == 1.0
    )
    assert draft_scores["line_coherence"] == 1.0 and draft_scores["explanation_quality"] == 1.0
    assert draft_scores["safety_consistent"] == 1.0 and "diagnosis_reasonable" not in draft_scores


def test_a_safety_case_is_checked_live_too(scored_app):
    make, posted, _ = scored_app
    critical_args = {**DRAFT_ARGS, "severity": "safety_critical"}
    api = make(
        {"r1": [triage_ok(severity="safety_critical")]}, [[("draft_work_order", critical_args)]]
    )
    intake_id = triaged(api)["done"]["intake_id"]
    dict(continued(api, intake_id))
    assert all({s.key: s.score for s in scores}["safety_consistent"] == 1.0 for _, scores in posted)


def test_scoring_never_breaks_the_request(seeded_db):
    def explode(*_):
        raise RuntimeError("LangSmith is down")

    scorer = OnlineScorer(lambda: nullcontext(seeded_db), post=explode, background=False)
    triage, agent = FakeTriage({"r1": [triage_ok()]}), FakeAgent([])
    deps = Deps(connect=lambda: nullcontext(seeded_db), embedder=FakeEmbedder(),
                triage_model=lambda: triage, agent_model=lambda: agent)  # fmt: skip
    api = TestClient(create_app(deps=deps, online=scorer))
    stream = events(api.post("/api/intakes", json=intake()))
    assert stream[-1][0] == "done"  # the counter got its answer


def test_declines_and_unresolved_bikes_are_not_scored(scored_app):
    make, posted, _ = scored_app
    api = make({"r1": [triage_ok(severity="safety_critical")]})
    intake_id = triaged(api)["done"]["intake_id"]
    posted.clear()
    api.post(f"/api/intakes/{intake_id}/decline", json={"staff": "sam", "waiver_signed": True})
    assert posted == []  # nothing drafted, nothing to check
