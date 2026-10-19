"""Graph logic with a scripted fake model: every path, no network."""

import threading
from contextlib import nullcontext

import pytest
from langchain_core.messages import AIMessage
from pydantic import ValidationError

from counterwrench.agent.graph import build_graph
from counterwrench.agent.nodes import Deps
from counterwrench.models import IntakeForm, RowAssessment
from counterwrench.rag.embed import FakeEmbedder

SLASH = "trek-slash-9-8-xt-gen-6-2024"


class FakeTriage:
    """Stands in for the triage chat model. `scripts` maps row_id to the responses that row's
    calls return, in order: a dict (validated as RowAssessment) or a string (a parse error)."""

    def __init__(self, scripts: dict[str, list]):
        self.scripts = {row_id: list(items) for row_id, items in scripts.items()}
        self.calls: dict[str, list] = {}
        self._lock = threading.Lock()

    def with_structured_output(self, schema, include_raw):
        return self

    def invoke(self, messages):
        row_id = messages[1].content.rsplit('Assess row "', 1)[1].split('"', 1)[0]
        with self._lock:
            self.calls.setdefault(row_id, []).append(messages)
            item = self.scripts[row_id].pop(0)
        if isinstance(item, str):
            return {"raw": AIMessage(item), "parsed": None, "parsing_error": ValueError(item)}
        try:
            parsed = RowAssessment.model_validate(item)
            return {"raw": AIMessage("ok"), "parsed": parsed, "parsing_error": None}
        except ValidationError as exc:
            return {"raw": AIMessage("bad"), "parsed": None, "parsing_error": exc}


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
    return build_graph(deps).invoke({"intake": form}), fake


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


def test_questions_stop_the_run_for_answers(seeded_db):
    result, _ = run(seeded_db, {"r1": [assessment(question_for_customer="Which gear?")]})
    assert result["outcome"] == "needs_answers"
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
