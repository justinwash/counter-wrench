"""Applying a mechanic's decision: the one place a work order leaves awaiting_review.

Used by the graph's human_review step and, in step 19, the API. The database refuses an
approval or rejection without reviewed_by and reviewed_at (migration 006), so this sets all
three in a single update.
"""

from __future__ import annotations

from typing import Literal, Self

import psycopg
from pydantic import BaseModel, Field, model_validator

from counterwrench.models import WorkOrderStatus


class ReviewDecision(BaseModel):
    decision: Literal["approve", "reject"]
    reviewer: str = Field(min_length=1)
    notes: str | None = None

    @model_validator(mode="after")
    def _rejections_need_a_reason(self) -> Self:
        if self.decision == "reject" and not (self.notes or "").strip():
            raise ValueError("a rejection needs notes saying why (it becomes feedback)")
        return self


class ReviewError(Exception):
    pass


def apply_review(conn: psycopg.Connection, work_order_id: int, review: ReviewDecision) -> str:
    status = WorkOrderStatus.APPROVED if review.decision == "approve" else WorkOrderStatus.REJECTED
    row = conn.execute(
        """
        UPDATE work_orders
        SET status = %s, reviewed_by = %s, reviewed_at = now(), review_notes = %s
        WHERE id = %s AND status = 'awaiting_review'
        RETURNING status
        """,
        (status.value, review.reviewer, review.notes, work_order_id),
    ).fetchone()
    if row is None:
        raise ReviewError(f"Work order {work_order_id} isn't awaiting review.")
    return row[0]
