"""The counter's intake flow, streamed as server-sent events.

    POST /intakes                  triage, then pause: `triaged`, `done` (awaiting_confirmation)
    POST /intakes/{id}/continue    create the work order: `draft`, `review`, `done`
    POST /intakes/{id}/revise      answers and note edits: the paused run ends as `revised`
                                   and a new run triages the updated intake
    POST /intakes/{id}/answers     the bike couldn't be resolved: pick it, or carry on without it

Every stream starts with `accepted` (except continue) and ends with `done` (or `error`).
Guardrails run before the graph sees any text, exactly as in the CLI (D-029).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from langgraph.types import Command
from pydantic import BaseModel, Field

from counterwrench.api.events import events_for, sse
from counterwrench.guardrails import apply_guardrails
from counterwrench.models import IntakeForm, LongText, ShortText
from counterwrench.tracing import run_metadata

log = logging.getLogger(__name__)
router = APIRouter(tags=["intakes"])
SSE = "text/event-stream"


def _thread(intake_id: str) -> dict:
    return {"configurable": {"thread_id": intake_id}}


def _run(cw, graph_input, intake_id: str, config: dict) -> Iterator[str]:
    try:
        for chunk in cw.graph.stream(graph_input, config, stream_mode="updates"):
            for node, update in chunk.items():
                for event, data in events_for(node, update):
                    yield sse(event, data)
    except Exception as exc:  # the stream has started, so report it as an event, not a 500
        log.exception("intake %s failed", intake_id)
        yield sse("error", {"intake_id": intake_id, "message": str(exc)[:300]})
        return
    state = cw.graph.get_state(_thread(intake_id))
    values, waiting = state.values, state.next or ()
    yield sse("done", {
        "intake_id": intake_id, "outcome": values.get("outcome"),
        "work_order_id": values.get("work_order_id"),
        "awaiting_confirmation": "confirm" in waiting,
        "awaiting_review": "human_review" in waiting,
    })  # fmt: skip


def _new_run(cw, intake: IntakeForm, previous: str | None = None) -> Iterator[str]:
    guarded = apply_guardrails(intake)
    flags = sorted({f.kind for f in guarded.flags})
    run_id = uuid.uuid4()
    intake_id = str(run_id)
    accepted = {"intake_id": intake_id, "run_id": intake_id, "previous": previous,
                "pii_redacted": guarded.pii_counts, "guardrail_flags": flags}  # fmt: skip
    yield sse("accepted", accepted)
    config = {**_thread(intake_id), "run_id": run_id, "run_name": "counterwrench", "tags": ["api"]}
    if cw.config is not None:
        config["metadata"] = run_metadata(
            cw.config, pii_redacted=guarded.pii_counts, guardrail_flags=flags,
            previous_intake=previous,
        )  # fmt: skip
    inputs = {"intake": guarded.intake, "run_id": intake_id, "source": "counter",
              "guardrail_note": guarded.mechanic_note(), "guardrail_flags": flags}  # fmt: skip
    yield from _run(cw, inputs, intake_id, config)


def _paused_at(cw, intake_id: str, node: str):
    state = cw.graph.get_state(_thread(intake_id))
    if not state.values:
        raise HTTPException(404, f"no intake {intake_id}")
    if node not in (state.next or ()):
        raise HTTPException(409, f"this intake isn't waiting at {node}")
    return state


@router.post("/intakes")
def submit(intake: IntakeForm, request: Request) -> StreamingResponse:
    return StreamingResponse(_new_run(request.app.state.cw, intake), media_type=SSE)


@router.post("/intakes/{intake_id}/continue")
def continue_to_draft(intake_id: str, request: Request) -> StreamingResponse:
    """Counter staff are done with the triage: draft the work order for the mechanic."""
    cw = request.app.state.cw
    _paused_at(cw, intake_id, "confirm")
    config = {**_thread(intake_id), "run_name": "counterwrench-continue"}
    return StreamingResponse(
        _run(cw, Command(resume={"action": "draft"}), intake_id, config), media_type=SSE
    )


def add_answers(
    prior: IntakeForm, questions: dict[str, str], new: dict[str, str]
) -> tuple[dict[str, str], dict[str, int]]:
    """Append this round's answers to each row's record, each with the question it answers.
    A bare "yes" means nothing on the next round, and replacing the earlier answer made the
    agent forget what it had been told, so it asked again (the loop Justin hit)."""
    answers, rounds = dict(prior.answers), dict(prior.question_rounds)
    for row_id, answer in new.items():
        question = questions.get(row_id) or "(staff added this)"
        entry = f"Asked: {question}\nAnswered: {answer}"
        answers[row_id] = f"{answers[row_id]}\n\n{entry}" if answers.get(row_id) else entry
        rounds[row_id] = rounds.get(row_id, 0) + 1
    return answers, rounds


class Revision(BaseModel):
    answers: dict[str, ShortText] = Field(default_factory=dict, description="row id -> answer")
    notes: dict[str, ShortText | None] = Field(
        default_factory=dict, description="row id -> replacement customer note"
    )
    general_notes: LongText | None = None


@router.post("/intakes/{intake_id}/revise")
def revise(intake_id: str, body: Revision, request: Request) -> StreamingResponse:
    """Answer the questions or fix the notes, then triage again. The paused run is finished
    as `revised` first, so its trace ends cleanly instead of hanging at the pause."""
    cw = request.app.state.cw
    state = _paused_at(cw, intake_id, "confirm")
    prior: IntakeForm = state.values["intake"]
    finish = {**_thread(intake_id), "run_name": "counterwrench-revised"}
    for _ in cw.graph.stream(Command(resume={"action": "revise"}), finish):
        pass
    rows = [r.model_copy(update={"note": body.notes[r.row_id]}) if r.row_id in body.notes else r
            for r in prior.rows]  # fmt: skip
    answers, rounds = add_answers(prior, state.values.get("questions") or {}, body.answers)
    data = {**prior.model_dump(), "rows": [r.model_dump() for r in rows],
            "answers": answers, "question_rounds": rounds}  # fmt: skip
    if "general_notes" in body.model_fields_set:
        data["general_notes"] = body.general_notes
    return StreamingResponse(
        _new_run(cw, IntakeForm.model_validate(data), previous=intake_id), media_type=SSE
    )


class Decline(BaseModel):
    staff: ShortText
    waiver_signed: bool = False


@router.post("/intakes/{intake_id}/decline")
def decline(intake_id: str, body: Decline, request: Request) -> StreamingResponse:
    """The customer doesn't want the work: keep a declined record and release the bike. A
    safety-critical decline needs a signed waiver (the database enforces it too)."""
    cw = request.app.state.cw
    state = _paused_at(cw, intake_id, "confirm")
    if state.values.get("escalated") and not body.waiver_signed:
        raise HTTPException(422, "safety-critical: the customer must sign the waiver first")
    config = {**_thread(intake_id), "run_name": "counterwrench-declined"}
    resume = Command(resume={"action": "decline", **body.model_dump()})
    return StreamingResponse(_run(cw, resume, intake_id, config), media_type=SSE)


class Answers(BaseModel):
    bike_id: str | None = Field(default=None, description="The catalog bike, once identified.")
    bike_unconfirmed: bool = Field(
        default=False,
        description="The customer doesn't know either: carry on without a catalog bike.",
    )


@router.post("/intakes/{intake_id}/answers")
def answer(intake_id: str, body: Answers, request: Request) -> StreamingResponse:
    """The bike couldn't be resolved, so the run stopped: re-run with the bike staff picked,
    or with the bike marked unconfirmed (labor only; the mechanic identifies it)."""
    cw = request.app.state.cw
    state = cw.graph.get_state(_thread(intake_id))
    if not state.values:
        raise HTTPException(404, f"no intake {intake_id}")
    if state.values.get("outcome") != "needs_answers":
        raise HTTPException(409, "this intake isn't waiting on the bike")
    if not body.bike_id and not body.bike_unconfirmed:
        raise HTTPException(422, "give bike_id, or bike_unconfirmed: true")
    prior: IntakeForm = state.values["intake"]
    update = ({"bike_id": body.bike_id, "bike_freetext": None} if body.bike_id
              else {"bike_unconfirmed": True})  # fmt: skip
    intake = IntakeForm.model_validate({**prior.model_dump(), **update})
    return StreamingResponse(_new_run(cw, intake, previous=intake_id), media_type=SSE)
