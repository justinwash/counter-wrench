"""Submitting an intake, and answering the question that stopped one.

Both stream server-sent events as the graph runs: `accepted`, `bike`, one `row` per complaint row
as its triage finishes, `route` (escalation and questions), `draft`, `review` (paused for the
mechanic) and finally `done`. Guardrails run before the graph, exactly as in the CLI (D-029).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from counterwrench.api.events import events_for, sse
from counterwrench.guardrails import apply_guardrails
from counterwrench.models import IntakeForm, ShortText
from counterwrench.tracing import run_metadata

log = logging.getLogger(__name__)
router = APIRouter(tags=["intakes"])


def _stream(cw, intake: IntakeForm, previous: str | None = None) -> Iterator[str]:
    guarded = apply_guardrails(intake)
    flags = sorted({f.kind for f in guarded.flags})
    run_id = uuid.uuid4()
    thread = {"configurable": {"thread_id": str(run_id)}}
    accepted = {"intake_id": str(run_id), "run_id": str(run_id), "previous": previous,
                "pii_redacted": guarded.pii_counts, "guardrail_flags": flags}  # fmt: skip
    yield sse("accepted", accepted)
    config = {**thread, "run_id": run_id, "run_name": "counterwrench", "tags": ["api"]}
    if cw.config is not None:
        config["metadata"] = run_metadata(
            cw.config, pii_redacted=guarded.pii_counts, guardrail_flags=flags,
            previous_intake=previous,
        )  # fmt: skip
    inputs = {"intake": guarded.intake, "run_id": str(run_id), "source": "counter",
              "guardrail_note": guarded.mechanic_note(), "guardrail_flags": flags}  # fmt: skip
    try:
        for chunk in cw.graph.stream(inputs, config, stream_mode="updates"):
            for node, update in chunk.items():
                for event, data in events_for(node, update):
                    yield sse(event, data)
    except Exception as exc:  # the stream has started, so report it as an event, not a 500
        log.exception("intake %s failed", run_id)
        yield sse("error", {"intake_id": str(run_id), "message": str(exc)[:300]})
        return
    values = cw.graph.get_state(thread).values
    yield sse("done", {"intake_id": str(run_id), "outcome": values.get("outcome"),
                       "work_order_id": values.get("work_order_id"),
                       "awaiting_review": bool(values.get("work_order_id"))})  # fmt: skip


@router.post("/intakes")
def submit(intake: IntakeForm, request: Request) -> StreamingResponse:
    return StreamingResponse(_stream(request.app.state.cw, intake), media_type="text/event-stream")


class Answers(BaseModel):
    answers: dict[str, ShortText] = Field(default_factory=dict, description="row id -> answer")
    bike_id: str | None = Field(
        default=None, description="The catalog bike, if the bike was the question."
    )


@router.post("/intakes/{intake_id}/answers")
def answer(intake_id: str, body: Answers, request: Request) -> StreamingResponse:
    """Re-run an intake that stopped for answers (the bike couldn't be resolved), with the
    answers added. Questions about rows don't stop a run (D-037): they're answered at review."""
    cw = request.app.state.cw
    state = cw.graph.get_state({"configurable": {"thread_id": intake_id}})
    if not state.values:
        raise HTTPException(404, f"no intake {intake_id}")
    if state.values.get("outcome") != "needs_answers":
        raise HTTPException(409, "this intake isn't waiting on answers")
    prior: IntakeForm = state.values["intake"]
    update: dict = {"answers": {**prior.answers, **body.answers}}
    if body.bike_id:
        update |= {"bike_id": body.bike_id, "bike_freetext": None}
    intake = IntakeForm.model_validate({**prior.model_dump(), **update})
    return StreamingResponse(
        _stream(cw, intake, previous=intake_id), media_type="text/event-stream"
    )
