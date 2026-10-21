"""The API's real routes, with scripted models and the seeded test database."""

import json
from contextlib import nullcontext

import pytest
from fakes import FakeAgent, FakeTriage
from fastapi.testclient import TestClient
from test_draft import DRAFT_ARGS, HIGHTOWER, triage_ok

from counterwrench.agent.nodes import Deps
from counterwrench.api.app import create_app
from counterwrench.rag.embed import FakeEmbedder


def client(db, triage_scripts, agent_turns=()):
    triage, agent = FakeTriage(triage_scripts), FakeAgent(list(agent_turns))
    deps = Deps(connect=lambda: nullcontext(db), embedder=FakeEmbedder(),
                triage_model=lambda: triage, agent_model=lambda: agent)  # fmt: skip
    return TestClient(create_app(deps=deps)), triage


def events(response) -> list[tuple[str, dict]]:
    out = []
    for block in response.text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        out.append((lines["event"], json.loads(lines["data"])))
    return out


def intake(note="Skips on the cogs I use most.", **overrides):
    return {"bike_id": HIGHTOWER, "rows": [{"row_id": "r1", "complaint": "skipping",
            "suspected_area": "chain", "note": note}], **overrides}  # fmt: skip


def test_picklists(seeded_db):
    api, _ = client(seeded_db, {})
    complaints = {c["value"]: c for c in api.get("/api/taxonomy").json()}
    areas = [a["value"] for a in complaints["skipping"]["areas"]]
    assert (
        "chain" in areas and areas[-1] == "unsure" and complaints["skipping"]["label"] == "Skipping"
    )
    found = api.get("/api/bikes", params={"q": "hightower"}).json()
    assert [b["bike_id"] for b in found] == [HIGHTOWER]
    assert len(api.get("/api/bikes").json()) > 10


def test_intake_streams_each_step_and_saves_a_counter_order(seeded_db):
    api, _ = client(seeded_db, {"r1": [triage_ok()]}, [[("draft_work_order", DRAFT_ARGS)]])
    stream = events(api.post("/api/intakes", json=intake()))
    names = [e for e, _ in stream]
    assert names == ["accepted", "bike", "row", "route", "draft", "review", "done"]
    done = stream[-1][1]
    assert done["outcome"] == "ready_to_draft" and done["awaiting_review"] is True
    source = seeded_db.execute("SELECT source FROM work_orders WHERE id = %s",
                               (done["work_order_id"],)).fetchone()[0]  # fmt: skip
    assert source == "counter"
    assert dict(stream)["row"]["severity"] == "needs_service"


def test_guardrails_run_before_the_graph(seeded_db):
    api, triage = client(seeded_db, {"r1": [triage_ok()]}, [[("draft_work_order", DRAFT_ARGS)]])
    stream = dict(events(api.post("/api/intakes", json=intake(note="Call me at (555) 222-3434."))))
    assert stream["accepted"]["pii_redacted"] == {"phone": 1}
    prompt = triage.calls["r1"][0][1].content
    assert "222-3434" not in prompt


def test_safety_escalation_is_announced(seeded_db):
    critical = {**DRAFT_ARGS, "severity": "safety_critical"}
    api, _ = client(seeded_db, {"r1": [triage_ok(severity="safety_critical")]},
                    [[("draft_work_order", critical)]])  # fmt: skip
    route = dict(events(api.post("/api/intakes", json=intake())))["route"]
    assert route["escalated"] is True and route["escalation_message"].startswith("DO NOT RIDE")


def test_answering_the_bike_question_reruns_with_the_bike(seeded_db):
    api, _ = client(seeded_db, {"r1": [triage_ok(), triage_ok()]},
                    [[("draft_work_order", DRAFT_ARGS)]])  # fmt: skip
    ambiguous = intake(bike_id=None, bike_freetext="Trek Marlin 7, not sure what year")
    first = dict(events(api.post("/api/intakes", json=ambiguous)))
    assert first["done"]["outcome"] == "needs_answers" and "bike" in first["route"]["questions"]
    rerun = dict(events(api.post(f"/api/intakes/{first['done']['intake_id']}/answers",
                                 json={"bike_id": HIGHTOWER})))  # fmt: skip
    assert rerun["accepted"]["previous"] == first["done"]["intake_id"]
    assert rerun["bike"]["bike_id"] == HIGHTOWER and rerun["done"]["awaiting_review"] is True


def test_answers_only_for_intakes_waiting_on_them(seeded_db):
    api, _ = client(seeded_db, {"r1": [triage_ok()]}, [[("draft_work_order", DRAFT_ARGS)]])
    done = dict(events(api.post("/api/intakes", json=intake())))["done"]
    assert api.post(f"/api/intakes/{done['intake_id']}/answers", json={}).status_code == 409
    assert api.post("/api/intakes/nope/answers", json={}).status_code == 404


# --- Orders: queue, detail, edits, review (19b) --------------------------------------------------


@pytest.fixture(autouse=True)
def no_tracing(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "false")  # no trace sharing or feedback in tests


def drafted(api) -> int:
    return dict(events(api.post("/api/intakes", json=intake())))["done"]["work_order_id"]


def test_review_queue_puts_safety_first_and_hides_eval_orders(seeded_db):
    critical = {**DRAFT_ARGS, "severity": "safety_critical"}
    turns = [[("draft_work_order", DRAFT_ARGS)], [("draft_work_order", critical)]]
    api, _ = client(seeded_db, {"r1": [triage_ok(), triage_ok(severity="safety_critical")]}, turns)
    routine, urgent = drafted(api), drafted(api)
    seeded_db.execute("UPDATE work_orders SET source = 'eval' WHERE id = %s", (routine,))
    queue = api.get("/api/orders", params={"status": "awaiting_review"}).json()
    assert [o["id"] for o in queue] == [urgent]
    with_eval = api.get("/api/orders", params={"include_eval": True}).json()
    assert [o["id"] for o in with_eval] == [urgent, routine]  # priority first


def test_order_detail_has_lines_reasons_sources_and_triage(seeded_db):
    api, _ = client(seeded_db, {"r1": [triage_ok()]}, [[("draft_work_order", DRAFT_ARGS)]])
    detail = api.get(f"/api/orders/{drafted(api)}").json()
    part = next(line for line in detail["lines"] if line["part_id"])
    assert part["name"] and part["compat_reasons"]
    assert detail["triage"]["assessments"]["r1"]["severity"] == "needs_service"
    assert detail["trace_url"] is None  # tracing off


def test_mechanic_edits_are_validated_like_drafts(seeded_db):
    api, _ = client(seeded_db, {"r1": [triage_ok()]}, [[("draft_work_order", DRAFT_ARGS)]])
    order_id = drafted(api)
    bad = {"editor": "sam", "labor_lines": [], "part_lines": [{"part_id": "sram-pg-1230-11-50"}]}
    refused = api.put(f"/api/orders/{order_id}/lines", json=bad)
    assert refused.status_code == 422 and "CASSETTE-INSTALL" in str(refused.json())
    good = {"editor": "sam", "labor_lines": [{"code": "CASSETTE-INSTALL"}, {"code": "INSPECT"}],
            "part_lines": [{"part_id": "sram-pg-1230-11-50"}]}  # fmt: skip
    detail = api.put(f"/api/orders/{order_id}/lines", json=good).json()
    assert detail["order"]["edited_by"] == "sam"
    assert detail["order"]["estimate_total_cents"] == sum(
        line["qty"] * line["unit_price_cents"] for line in detail["lines"]
    )


def test_review_resumes_the_drafting_run(seeded_db):
    api, _ = client(seeded_db, {"r1": [triage_ok()]}, [[("draft_work_order", DRAFT_ARGS)]])
    order_id = drafted(api)
    no_reason = {"decision": "reject", "reviewer": "sam"}
    assert api.post(f"/api/orders/{order_id}/review", json=no_reason).status_code == 422
    ok = api.post(f"/api/orders/{order_id}/review", json={"decision": "approve", "reviewer": "sam"})
    assert ok.json() == {"id": order_id, "status": "approved", "resumed_graph": True}
    again = api.post(
        f"/api/orders/{order_id}/review", json={"decision": "approve", "reviewer": "sam"}
    )
    assert again.status_code == 409
    assert api.put(f"/api/orders/{order_id}/lines", json={"editor": "sam"}).status_code == 422


def test_orders_made_outside_the_api_are_reviewed_directly(seeded_db):
    from counterwrench.tools.work_orders import DraftWorkOrderArgs, draft_work_order

    saved = draft_work_order(seeded_db, DraftWorkOrderArgs.model_validate(DRAFT_ARGS))
    api, _ = client(seeded_db, {})
    reject = {"decision": "reject", "reviewer": "sam", "notes": "wrong cassette"}
    result = api.post(f"/api/orders/{saved.work_order_id}/review", json=reject)
    assert result.json()["status"] == "rejected"
    assert result.json()["resumed_graph"] is False


def test_a_paused_review_survives_a_restart(seeded_db, db_url):
    from counterwrench.api.app import postgres_checkpointer

    deps_args = {"r1": [triage_ok()]}, [[("draft_work_order", DRAFT_ARGS)]]
    triage, agent = FakeTriage(deps_args[0]), FakeAgent(deps_args[1])
    deps = Deps(connect=lambda: nullcontext(seeded_db), embedder=FakeEmbedder(),
                triage_model=lambda: triage, agent_model=lambda: agent)  # fmt: skip
    before = TestClient(create_app(deps=deps, checkpointer=postgres_checkpointer(db_url)))
    order_id = drafted(before)
    after = TestClient(create_app(deps=deps, checkpointer=postgres_checkpointer(db_url)))  # restart
    result = after.post(
        f"/api/orders/{order_id}/review", json={"decision": "approve", "reviewer": "sam"}
    )
    assert result.json()["resumed_graph"] is True and result.json()["status"] == "approved"
