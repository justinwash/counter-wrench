"""The API's real routes, with scripted models and the seeded test database."""

import json
from contextlib import nullcontext

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
