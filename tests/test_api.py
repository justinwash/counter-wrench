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


def triaged(api, body=None) -> dict:
    return dict(events(api.post("/api/intakes", json=body or intake())))


def continued(api, intake_id: str) -> list[tuple[str, dict]]:
    return events(api.post(f"/api/intakes/{intake_id}/continue"))


def test_intake_pauses_after_triage_then_drafts_on_continue(seeded_db):
    api, _ = client(seeded_db, {"r1": [triage_ok()]}, [[("draft_work_order", DRAFT_ARGS)]])
    first = events(api.post("/api/intakes", json=intake()))
    assert [e for e, _ in first] == ["accepted", "bike", "row", "route", "triaged", "done"]
    done = first[-1][1]
    assert done["awaiting_confirmation"] is True and done["work_order_id"] is None
    assert seeded_db.execute("SELECT count(*) FROM work_orders").fetchone()[0] == 0
    second = continued(api, done["intake_id"])
    assert [e for e, _ in second] == ["draft", "review", "done"]
    finished = second[-1][1]
    assert finished["awaiting_review"] is True and finished["work_order_id"]
    source = seeded_db.execute("SELECT source FROM work_orders WHERE id = %s",
                               (finished["work_order_id"],)).fetchone()[0]  # fmt: skip
    assert source == "counter"
    assert api.post(f"/api/intakes/{done['intake_id']}/continue").status_code == 409


def test_guardrails_run_before_the_graph(seeded_db):
    api, triage = client(seeded_db, {"r1": [triage_ok()]})
    stream = triaged(api, intake(note="Call me at (555) 222-3434."))
    assert stream["accepted"]["pii_redacted"] == {"phone": 1}
    assert "222-3434" not in triage.calls["r1"][0][1].content


def test_safety_escalation_is_announced(seeded_db):
    api, _ = client(seeded_db, {"r1": [triage_ok(severity="safety_critical")]})
    route = triaged(api)["route"]
    assert route["escalated"] is True and route["escalation_message"].startswith("DO NOT RIDE")


def test_revise_finishes_the_old_run_and_triages_again_with_answers(seeded_db):
    asks = triage_ok(question_for_customer="Which gears skip?")
    api, triage = client(seeded_db, {"r1": [asks, triage_ok()]})
    first = triaged(api)
    assert first["route"]["questions"] == {"r1": "Which gears skip?"}
    old_id = first["done"]["intake_id"]
    body = {"answers": {"r1": "Only the two biggest cogs"}, "notes": {"r1": "Skips under power"}}
    second = dict(events(api.post(f"/api/intakes/{old_id}/revise", json=body)))
    assert second["accepted"]["previous"] == old_id and second["done"]["awaiting_confirmation"]
    retriage_prompt = triage.calls["r1"][1][1].content
    assert "Only the two biggest cogs" in retriage_prompt and "Skips under power" in retriage_prompt
    old = api.app.state.cw.graph.get_state({"configurable": {"thread_id": old_id}})
    assert old.values["outcome"] == "revised" and not old.next  # finished, not left hanging


def test_answering_the_bike_question_reruns_with_the_bike(seeded_db):
    api, _ = client(seeded_db, {"r1": [triage_ok(), triage_ok()]})
    first = triaged(api, intake(bike_id=None, bike_freetext="Trek Marlin 7, not sure what year"))
    assert first["done"]["outcome"] == "needs_answers" and "bike" in first["route"]["questions"]
    rerun = dict(events(api.post(f"/api/intakes/{first['done']['intake_id']}/answers",
                                 json={"bike_id": HIGHTOWER})))  # fmt: skip
    assert rerun["accepted"]["previous"] == first["done"]["intake_id"]
    assert rerun["bike"]["bike_id"] == HIGHTOWER and rerun["done"]["awaiting_confirmation"]


def test_unknown_bike_year_drafts_labor_only_with_a_note(seeded_db):
    labor_only = {**DRAFT_ARGS, "part_lines": []}
    api, _ = client(seeded_db, {"r1": [triage_ok(), triage_ok()]},
                    [[("draft_work_order", labor_only)]])  # fmt: skip
    first = triaged(api, intake(bike_id=None, bike_freetext="Trek Marlin 7, not sure what year"))
    rerun = dict(events(api.post(f"/api/intakes/{first['done']['intake_id']}/answers",
                                 json={"bike_unconfirmed": True})))  # fmt: skip
    assert rerun["bike"]["bike_id"] is None and rerun["bike"]["question"] is None
    assert rerun["done"]["awaiting_confirmation"] is True
    order_id = dict(continued(api, rerun["done"]["intake_id"]))["done"]["work_order_id"]
    notes = seeded_db.execute("SELECT mechanic_notes FROM work_orders WHERE id = %s",
                              (order_id,)).fetchone()[0]  # fmt: skip
    assert "Bike unconfirmed" in notes and "call the customer" in notes


def test_a_safety_critical_decline_needs_a_signed_waiver(seeded_db):
    api, _ = client(seeded_db, {"r1": [triage_ok(severity="safety_critical")]})
    intake_id = triaged(api)["done"]["intake_id"]
    unsigned = api.post(f"/api/intakes/{intake_id}/decline", json={"staff": "sam"})
    assert unsigned.status_code == 422
    done = dict(events(api.post(f"/api/intakes/{intake_id}/decline",
                                json={"staff": "sam", "waiver_signed": True})))["done"]  # fmt: skip
    assert done["outcome"] == "declined"
    row = seeded_db.execute(
        "SELECT status, severity, waiver_signed, reviewed_by, review_notes "
        "FROM work_orders WHERE id = %s", (done["work_order_id"],),
    ).fetchone()  # fmt: skip
    assert row[:4] == ("declined", "safety_critical", True, "sam") and "Bike released" in row[4]
    state = api.app.state.cw.graph.get_state({"configurable": {"thread_id": intake_id}})
    assert not state.next  # the run finished


def test_answers_only_for_intakes_waiting_on_them(seeded_db):
    api, _ = client(seeded_db, {"r1": [triage_ok()]})
    done = triaged(api)["done"]
    assert (
        api.post(
            f"/api/intakes/{done['intake_id']}/answers", json={"bike_unconfirmed": True}
        ).status_code
        == 409
    )
    assert api.post("/api/intakes/nope/answers", json={"bike_unconfirmed": True}).status_code == 404


# --- Orders: queue, detail, edits, review (19b) --------------------------------------------------


@pytest.fixture(autouse=True)
def no_tracing(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "false")  # no trace sharing or feedback in tests


def drafted(api) -> int:
    intake_id = triaged(api)["done"]["intake_id"]
    return dict(continued(api, intake_id))["done"]["work_order_id"]


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


def test_serves_the_built_ui_with_deep_links(seeded_db, tmp_path, monkeypatch):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<title>CounterWrench</title>")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    monkeypatch.setenv("CW_STATIC_DIR", str(tmp_path))
    api, _ = client(seeded_db, {})
    assert "CounterWrench" in api.get("/").text
    assert "CounterWrench" in api.get("/orders/12").text  # the UI's router takes it from here
    assert api.get("/assets/app.js").text == "console.log(1)"
    assert api.get("/api/no-such-route").status_code == 404  # API misses aren't the UI
    assert api.get("/api/taxonomy").status_code == 200


def test_rate_limit_applies_only_to_requests_that_spend_money(seeded_db):
    triage, agent = FakeTriage({"r1": [triage_ok(), triage_ok()]}), FakeAgent([])
    deps = Deps(connect=lambda: nullcontext(seeded_db), embedder=FakeEmbedder(),
                triage_model=lambda: triage, agent_model=lambda: agent)  # fmt: skip
    api = TestClient(create_app(deps=deps, rate_limit_per_hour=2))
    assert api.post("/api/intakes", json=intake()).status_code == 200
    assert api.post("/api/intakes", json=intake()).status_code == 200
    blocked = api.post("/api/intakes", json=intake())
    assert blocked.status_code == 429 and int(blocked.headers["retry-after"]) > 0
    assert api.get("/api/taxonomy").status_code == 200  # reads aren't limited
    other = api.post("/api/intakes", json=intake(), headers={"x-forwarded-for": "10.0.0.9"})
    assert other.status_code == 200  # per client, not global


def test_labor_menu_and_part_options_for_the_edit_screen(seeded_db):
    api, _ = client(seeded_db, {"r1": [triage_ok()]}, [[("draft_work_order", DRAFT_ARGS)]])
    menu = {m["code"]: m for m in api.get("/api/labor-menu").json()}
    assert menu["CASSETTE-INSTALL"]["price_cents"] > 0 and len(menu) > 20
    order_id = drafted(api)
    options = api.get(
        f"/api/orders/{order_id}/part-options", params={"category": "cassette"}
    ).json()
    ids = [p["part_id"] for p in options["compatible"]]
    assert "sram-pg-1230-11-50" in ids and "shimano-cs-m7100-10-51" not in ids  # wrong freehub
    assert (
        api.get("/api/orders/999999/part-options", params={"category": "cassette"}).status_code
        == 404
    )


# --- Question rounds: no loops ------------------------------------------------------------------


def asks(question):
    return triage_ok(question_for_customer=question)


def revised(api, intake_id, answer):
    stream = events(api.post(f"/api/intakes/{intake_id}/revise", json={"answers": {"r1": answer}}))
    return dict(stream)


def test_each_answer_is_kept_with_its_question_across_rounds(seeded_db):
    from counterwrench.agent.nodes import ALREADY_ASKED

    first_q, second_q = "Do they squeal when wet?", "Does it happen on dry days too?"
    api, triage = client(seeded_db, {"r1": [asks(first_q), asks(second_q), triage_ok()]})
    first = triaged(api)
    second = revised(api, first["done"]["intake_id"], "Only when it's wet")
    third = revised(api, second["done"]["intake_id"], "No, dry days are fine")
    assert third["done"]["awaiting_confirmation"] is True

    prompts = [call[1].content for call in triage.calls["r1"]]
    assert ALREADY_ASKED not in prompts[0]  # a first look is unchanged
    assert f"Asked: {first_q}\nAnswered: Only when it's wet" in prompts[1]
    # Round two still carries round one: the earlier answer isn't replaced.
    assert f"Asked: {first_q}\nAnswered: Only when it's wet" in prompts[2]
    assert f"Asked: {second_q}\nAnswered: No, dry days are fine" in prompts[2]
    assert ALREADY_ASKED in prompts[1] and ALREADY_ASKED in prompts[2]


def test_triage_stops_asking_after_two_rounds_and_tells_the_mechanic(seeded_db):
    api, _ = client(seeded_db, {"r1": [asks("Q1?"), asks("Q2?"), asks("Q3, reworded?")]},
                    [[("draft_work_order", DRAFT_ARGS)]])  # fmt: skip
    first = triaged(api)
    second = revised(api, first["done"]["intake_id"], "A1")
    third = revised(api, second["done"]["intake_id"], "A2")

    assert third["row_unresolved"] == {"row_id": "r1", "question": "Q3, reworded?"}
    assert third["row"]["question_for_customer"] is None  # no third question for the counter
    assert third["route"]["questions"] == {} and third["done"]["outcome"] == "ready_to_draft"
    order_id = dict(continued(api, third["done"]["intake_id"]))["done"]["work_order_id"]
    notes = seeded_db.execute("SELECT mechanic_notes FROM work_orders WHERE id = %s",
                              (order_id,)).fetchone()[0]  # fmt: skip
    assert "Still unclear after 2 rounds of questions; check in person: r1: Q3, reworded?" in notes


def test_an_answer_with_no_recorded_question_is_still_kept(seeded_db):
    from counterwrench.api.intakes import add_answers
    from counterwrench.models import IntakeForm

    prior = IntakeForm.model_validate(intake())
    answers, rounds = add_answers(prior, {}, {"r1": "It only started last week"})
    assert answers["r1"] == "Asked: (staff added this)\nAnswered: It only started last week"
    assert rounds == {"r1": 1}
