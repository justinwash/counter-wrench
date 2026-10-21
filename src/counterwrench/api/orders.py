"""Work orders: the review queue, order detail, line edits, and the mechanic's decision.

A review resumes the graph that drafted the order when its paused run is in the checkpointer
(orders from the API), so the decision is part of that run's trace; orders made elsewhere (CLI,
evals) are reviewed directly. Either way `apply_review` is the only code that changes status.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from langgraph.types import Command
from psycopg.rows import dict_row
from pydantic import BaseModel

from counterwrench.agent.review import ReviewDecision, ReviewError, apply_review
from counterwrench.compat.engine import check
from counterwrench.compat.lookup import load_bike, load_part, load_rules
from counterwrench.models import WheelPosition
from counterwrench.tools.work_orders import EditLinesArgs, edit_lines
from counterwrench.tracing import public_trace_url, read_run

log = logging.getLogger(__name__)
router = APIRouter(tags=["orders"])


class OrderSummary(BaseModel):
    id: int
    status: str
    severity: str
    priority: bool
    bike: str
    estimate_total_cents: int
    created_at: datetime
    source: str
    edited: bool


@router.get("/orders")
def orders(
    request: Request, status: str | None = None, include_eval: bool = False
) -> list[OrderSummary]:
    """The review queue is `status=awaiting_review`: safety-critical first, then newest."""
    with request.app.state.cw.deps.connect() as conn:
        rows = (
            conn.cursor(row_factory=dict_row)
            .execute(
                """
            SELECT id, status, severity, priority, coalesce(bike_id, bike_freetext) AS bike,
                   estimate_total_cents, created_at, source, edited_by IS NOT NULL AS edited
            FROM work_orders
            WHERE (%(status)s::text IS NULL OR status = %(status)s)
              AND (%(eval)s OR source <> 'eval')
            ORDER BY priority DESC, created_at DESC LIMIT 200
            """,
                {"status": status, "eval": include_eval},
            )
            .fetchall()
        )
    return [OrderSummary(**r) for r in rows]


def _thread(order: dict) -> dict | None:
    return (
        {"configurable": {"thread_id": str(order["langsmith_run_id"])}}
        if order["langsmith_run_id"]
        else None
    )


def _detail(cw, order_id: int) -> dict:
    with cw.deps.connect() as conn:
        cur = conn.cursor(row_factory=dict_row)
        order = cur.execute("SELECT * FROM work_orders WHERE id = %s", (order_id,)).fetchone()
        if order is None:
            raise HTTPException(404, f"no work order {order_id}")
        lines = cur.execute(
            """
            SELECT l.labor_code, l.part_id, l.qty, l.unit_price_cents, l.position, l.unverified,
                   l.unverified_reason, coalesce(m.name, p.name) AS name
            FROM work_order_lines l
            LEFT JOIN labor_menu m ON m.code = l.labor_code
            LEFT JOIN parts p ON p.id = l.part_id
            WHERE l.work_order_id = %s ORDER BY l.id
            """,
            (order_id,),
        ).fetchall()
        bike = load_bike(conn, order["bike_id"]) if order["bike_id"] else None
        rules = load_rules(conn) if bike else None
        for line in lines:  # why each part fits (or why it's unverified), for the mechanic
            if line["part_id"] and bike:
                part = load_part(conn, line["part_id"])
                position = WheelPosition(line["position"]) if line["position"] else None
                try:
                    line["compat_reasons"] = check(bike, part, rules, position).reasons
                except ValueError as exc:
                    line["compat_reasons"] = [str(exc)]
        sources = cur.execute(
            "SELECT id, title, heading FROM doc_chunks WHERE id = ANY(%s)", (order["citations"],)
        ).fetchall()
    triage = None
    thread = _thread(order)
    if thread:
        values = cw.graph.get_state(thread).values
        if values:
            triage = {
                "assessments": {k: a.model_dump(mode="json")
                                for k, a in values.get("assessments", {}).items()},
                "questions": values.get("questions") or {},
                "escalation_message": values.get("escalation_message"),
            }  # fmt: skip
    return {"order": order, "lines": lines, "sources": sources, "triage": triage,
            "trace_url": _trace_url(cw, order)}  # fmt: skip


def _trace_url(cw, order: dict) -> str | None:
    if order["trace_url"] or not order["langsmith_run_id"]:
        return order["trace_url"]
    try:
        url = public_trace_url(order["langsmith_run_id"], timeout_s=5)
    except Exception:  # LangSmith being slow or down mustn't break the order page
        log.warning("couldn't share the trace for order %s", order["id"], exc_info=True)
        return None
    if url:
        with cw.deps.connect() as conn:
            conn.execute("UPDATE work_orders SET trace_url = %s WHERE id = %s", (url, order["id"]))
    return url


@router.get("/orders/{order_id}")
def order(order_id: int, request: Request) -> dict:
    return _detail(request.app.state.cw, order_id)


@router.put("/orders/{order_id}/lines")
def edit(order_id: int, body: EditLinesArgs, request: Request) -> dict:
    """Replace the lines of a draft awaiting review, checked like the agent's own drafts."""
    cw = request.app.state.cw
    with cw.deps.connect() as conn:
        problems = edit_lines(conn, order_id, body)
    if problems:
        raise HTTPException(422, {"problems": problems})
    return _detail(cw, order_id)


@router.post("/orders/{order_id}/review")
def review(order_id: int, decision: ReviewDecision, request: Request) -> dict:
    cw = request.app.state.cw
    with cw.deps.connect() as conn:
        order = (
            conn.cursor(row_factory=dict_row)
            .execute(
                "SELECT id, langsmith_run_id, edited_by FROM work_orders WHERE id = %s", (order_id,)
            )
            .fetchone()
        )
    if order is None:
        raise HTTPException(404, f"no work order {order_id}")
    thread = _thread(order)
    paused = thread and "human_review" in (cw.graph.get_state(thread).next or ())
    try:
        if paused:  # finish the drafting run, so the decision lands in its trace
            cw.graph.invoke(
                Command(resume=decision.model_dump()),
                {**thread, "run_name": "counterwrench-review"},
            )
            with cw.deps.connect() as conn:
                status = conn.execute(
                    "SELECT status FROM work_orders WHERE id = %s", (order_id,)
                ).fetchone()[0]
        else:
            with cw.deps.connect() as conn:
                status = apply_review(conn, order_id, decision)
    except ReviewError as exc:
        raise HTTPException(409, str(exc)) from exc
    _send_feedback(order, decision)
    return {"id": order_id, "status": status, "resumed_graph": bool(paused)}


def _send_feedback(order: dict, decision: ReviewDecision) -> None:
    """The mechanic's verdict as LangSmith feedback on the drafting run: the production signal
    online evaluation builds on (step 21). Best effort; the review itself already happened."""
    if not order["langsmith_run_id"] or os.environ.get("LANGSMITH_TRACING") != "true":
        return
    try:
        from langsmith import Client

        client, run_id = Client(), order["langsmith_run_id"]
        project = read_run(client, run_id).session_id  # feedback without it is deprecated
        approved = 1 if decision.decision == "approve" else 0
        client.create_feedback(run_id, key="mechanic_decision", score=approved,
                               comment=decision.notes, session_id=project,
                               source_info={"reviewer": decision.reviewer})  # fmt: skip
        client.create_feedback(run_id, key="mechanic_edited_lines", session_id=project,
                               score=1 if order["edited_by"] else 0)  # fmt: skip
    except Exception:
        log.warning("couldn't send review feedback for order %s", order["id"], exc_info=True)
