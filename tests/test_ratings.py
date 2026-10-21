"""Thumbs up/down on orders: what is stored, and what reaches LangSmith (a recording sink here)."""

from contextlib import nullcontext

import pytest
from fakes import FakeAgent, FakeTriage
from fastapi.testclient import TestClient
from test_api import continued, intake, triaged
from test_draft import DRAFT_ARGS, triage_ok

from counterwrench.agent.nodes import Deps
from counterwrench.api.app import create_app
from counterwrench.rag.embed import FakeEmbedder


class Recorder:
    def __init__(self):
        self.rated_calls, self.queued, self.candidates = [], {}, {}

    def rated(self, run_id, vote):
        self.rated_calls.append((run_id, vote.rater, vote.rating, vote.reason))

    def set_queued(self, run_id, queued, reasons):
        self.queued[run_id] = reasons if queued else None

    def set_candidate(self, order_id, candidate):
        self.candidates[order_id] = candidate


@pytest.fixture(autouse=True)
def no_tracing(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "false")


@pytest.fixture
def rated_order(seeded_db):
    sink = Recorder()
    triage, agent = (
        FakeTriage({"r1": [triage_ok()]}),
        FakeAgent([[("draft_work_order", DRAFT_ARGS)]]),
    )
    deps = Deps(connect=lambda: nullcontext(seeded_db), embedder=FakeEmbedder(),
                triage_model=lambda: triage, agent_model=lambda: agent)  # fmt: skip
    api = TestClient(create_app(deps=deps, ratings=sink))
    intake_id = triaged(api, intake())["done"]["intake_id"]
    order_id = dict(continued(api, intake_id))["done"]["work_order_id"]
    draft_run = str(
        seeded_db.execute(
            "SELECT draft_run_id FROM work_orders WHERE id = %s", (order_id,)
        ).fetchone()[0]
    )
    return api, sink, order_id, draft_run


def vote(api, order_id, rater, rating, reason=None):
    body = {"rater": rater, "rating": rating, **({"reason": reason} if reason else {})}
    return api.post(f"/api/orders/{order_id}/rating", json=body)


def test_a_thumbs_up_is_a_candidate_never_a_golden(rated_order):
    api, sink, order_id, draft_run = rated_order
    assert vote(api, order_id, "sam", "up").status_code == 200
    assert sink.rated_calls == [(draft_run, "sam", "up", None)]
    assert sink.queued[draft_run] is None
    candidate = sink.candidates[order_id]
    assert candidate["inputs"]["intake"] and candidate["outputs"]["lines"]


def test_a_thumbs_down_needs_a_reason_and_goes_to_the_queue(rated_order):
    api, sink, order_id, draft_run = rated_order
    assert vote(api, order_id, "sam", "down").status_code == 422
    assert vote(api, order_id, "sam", "down", "   ").status_code == 422
    assert sink.rated_calls == []  # nothing happened
    assert vote(api, order_id, "sam", "down", "wrong cassette").status_code == 200
    assert sink.queued[draft_run] == ["sam: wrong cassette"]
    assert sink.candidates[order_id] is None


def test_one_vote_per_person_and_changing_it_undoes_the_effects(rated_order):
    api, sink, order_id, draft_run = rated_order
    vote(api, order_id, "sam", "down", "wrong cassette")
    shown = vote(api, order_id, "sam", "up").json()
    assert [(v["rater"], v["rating"]) for v in shown] == [("sam", "up")]
    assert sink.queued[draft_run] is None  # no longer queued
    assert sink.candidates[order_id] is not None
    assert [r[1:3] for r in sink.rated_calls] == [("sam", "down"), ("sam", "up")]


def test_any_thumbs_down_keeps_it_out_of_the_candidates(rated_order):
    api, sink, order_id, draft_run = rated_order
    vote(api, order_id, "sam", "up")
    vote(api, order_id, "alex", "down", "price is off")
    assert sink.queued[draft_run] == ["alex: price is off"]
    assert sink.candidates[order_id] is None
    vote(api, order_id, "alex", "up")
    assert sink.queued[draft_run] is None and sink.candidates[order_id] is not None


def test_votes_show_on_the_order(rated_order):
    api, _, order_id, _ = rated_order
    vote(api, order_id, "sam", "up")
    vote(api, order_id, "alex", "down", "price is off")
    ratings = api.get(f"/api/orders/{order_id}").json()["ratings"]
    assert {(r["rater"], r["rating"], r["reason"]) for r in ratings} == {
        ("sam", "up", None),
        ("alex", "down", "price is off"),
    }


def test_rating_a_missing_order_is_a_404(rated_order):
    api, _, _, _ = rated_order
    assert vote(api, 999999, "sam", "up").status_code == 404


def test_a_sink_failure_does_not_lose_the_vote(rated_order):
    api, sink, order_id, _ = rated_order

    def broken(*_):
        raise RuntimeError("LangSmith is down")

    sink.rated = sink.set_queued = sink.set_candidate = broken
    assert vote(api, order_id, "sam", "up").status_code == 200
    assert len(api.get(f"/api/orders/{order_id}").json()["ratings"]) == 1
