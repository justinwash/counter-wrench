"""Turn one graph run (final state plus the saved work order) into the RunOutput evaluators read.

The draft is read back from the database rather than from the model's tool arguments: the
evaluators should score what was actually saved, after code injected the bike and severity.
"""

from __future__ import annotations

import psycopg

from evals.run_output import AssessmentOut, ChunkOut, DraftOut, LineOut, RunOutput, ToolCall


def load_draft(conn: psycopg.Connection, work_order_id: int) -> DraftOut:
    order = conn.execute(
        "SELECT status, severity, priority, estimate_total_cents, customer_explanation, "
        "mechanic_notes, intake FROM work_orders WHERE id = %s",
        (work_order_id,),
    ).fetchone()
    if order is None:
        raise LookupError(f"work order {work_order_id} not found")
    lines = conn.execute(
        "SELECT labor_code, part_id, qty, unit_price_cents, position, unverified, "
        "unverified_reason FROM work_order_lines WHERE work_order_id = %s ORDER BY id",
        (work_order_id,),
    ).fetchall()
    status, severity, priority, total, explanation, notes, intake = order
    return DraftOut(
        work_order_id=work_order_id, status=status, severity=severity, priority=priority,
        estimate_total_cents=total, customer_explanation=explanation, mechanic_notes=notes,
        stored_intake=intake,
        lines=[
            LineOut(kind="labor" if code else "part", code=code, part_id=part_id, qty=qty,
                    unit_price_cents=price, position=position, unverified=unverified,
                    unverified_reason=reason)
            for code, part_id, qty, price, position, unverified, reason in lines
        ],
    )  # fmt: skip


def build_run_output(state: dict, conn: psycopg.Connection) -> RunOutput:
    bike = state.get("bike")
    assessments = {
        row_id: AssessmentOut(
            row_id=row_id, severity=a.severity.value, agrees=a.agrees_with_suspected_area,
            likely_causes=a.likely_causes, disagreement_reason=a.disagreement_reason,
            question=a.question_for_customer, suggested_labor=list(a.suggested_labor),
            citations=a.citations,
        )
        for row_id, a in state.get("assessments", {}).items()
    }  # fmt: skip
    row_chunks = {
        row_id: [ChunkOut(chunk_id=h.chunk_id, heading=h.heading, content=h.content) for h in hits]
        for row_id, hits in state.get("row_chunks", {}).items()
    }
    order_id = state.get("work_order_id")
    return RunOutput(
        bike_id=bike.id if bike else None,
        assessments=assessments,
        row_chunks=row_chunks,
        failed_rows=sorted(state.get("failed_rows", {})),
        escalated=bool(state.get("escalated")),
        questions=state.get("questions", {}),
        outcome=state["outcome"],
        draft=load_draft(conn, order_id) if order_id else None,
        tool_calls=[ToolCall(tool=c["tool"], args=c["args"]) for c in state.get("tool_calls", [])],
        triage_retries=state.get("triage_retries", 0),
    )
