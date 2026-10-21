"""The Evals, Explore and live-score views: what they read, and that they fail soft."""

import pytest
from test_api import client, continued, triaged
from test_draft import DRAFT_ARGS, HIGHTOWER, triage_ok


@pytest.fixture(autouse=True)
def no_tracing(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "false")


def test_calibration_matches_the_documented_numbers(seeded_db):
    api, _ = client(seeded_db, {})
    body = api.get("/api/evals/calibration").json()
    assert (body["n_items"], body["justin_passed"], body["justin_failed"]) == (40, 33, 7)
    v3 = next(r for r in body["rubrics"] if r["version"] == "v3")
    diagnosis = next(j for j in v3["judges"] if j["judge"] == "diagnosis_reasonable")
    held = next(s for s in diagnosis["splits"] if s["split"] == "heldout")
    assert (
        round(held["metrics"]["accuracy"], 2) == 0.88 and round(held["metrics"]["kappa"], 2) == 0.60
    )
    explanation = next(j for j in v3["judges"] if j["judge"] == "explanation_quality")
    held = next(s for s in explanation["splits"] if s["split"] == "heldout")
    assert round(held["metrics"]["kappa"], 2) == -0.20  # the judge that failed, reported as it is
    confusion = held["confusion"]
    assert sum(confusion.values()) == held["metrics"]["n"]


def test_every_calibration_item_carries_both_rubrics_and_justins_grade(seeded_db):
    api, _ = client(seeded_db, {})
    items = api.get("/api/evals/calibration").json()["items"]
    assert len(items) == 40
    assert all(
        set(i["verdicts"]) == {"v2", "v3"} and i["justin"] in ("pass", "fail") for i in items
    )


def test_results_snapshot_has_every_experiment_and_a_confusion_matrix(seeded_db):
    api, _ = client(seeded_db, {})
    snap = api.get("/api/evals/results").json()
    assert [e["id"] for e in snap["experiments"]][:2] == ["E-001b", "E-002"]
    last = snap["experiments"][-1]
    escalated = last["evaluators"]["safety_escalated"]
    assert escalated["is_safety"] and escalated["slices"]["all"]["mean"] > 0.5
    assert (
        escalated["slices"]["safety"]["n"] > 0
    )  # the "safety" slice and the flag no longer collide
    assert last["confusion"]["labels"][0] == "safety_critical"
    assert sum(c["count"] for c in last["confusion"]["cells"]) > 100


def test_search_shows_ranked_chunks_and_rejects_empty_queries(seeded_db):
    api, _ = client(seeded_db, {})
    assert api.get("/api/explore/search", params={"q": "  "}).status_code == 422
    hits = api.get("/api/explore/search", params={"q": "chain skips under load"}).json()
    assert 0 < len(hits) <= 8 and {"chunk_id", "title", "score"} <= set(hits[0])


def test_compat_verdict_comes_with_reasons_and_specs(seeded_db):
    api, _ = client(seeded_db, {})
    parts = api.get("/api/explore/parts").json()
    cassette = next(p for p in parts if p["category"] == "cassette")
    view = api.get(
        "/api/explore/compat", params={"bike_id": HIGHTOWER, "part_id": cassette["part_id"]}
    ).json()
    assert view["bike_name"] and view["results"][0]["status"] in (
        "compatible",
        "incompatible",
        "unknown",
    )
    assert view["results"][0]["reasons"] and view["bike_specs"] and view["part_specs"]
    assert (
        api.get(
            "/api/explore/compat", params={"bike_id": "nope", "part_id": cassette["part_id"]}
        ).status_code
        == 404
    )


def test_live_scores_say_so_when_tracing_is_off(seeded_db):
    api, _ = client(seeded_db, {"r1": [triage_ok()]}, [[("draft_work_order", DRAFT_ARGS)]])
    intake_id = triaged(api)["done"]["intake_id"]
    order_id = dict(continued(api, intake_id))["done"]["work_order_id"]
    body = api.get(f"/api/orders/{order_id}/scores").json()
    assert body["available"] is False and "off" in body["reason"]
    assert api.get("/api/orders/999999/scores").status_code == 404
