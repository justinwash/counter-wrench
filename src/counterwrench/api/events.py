"""Graph progress as server-sent events, for the counter screen to fill row by row.

The graph streams one update per node as it finishes; `events_for` turns each into the events
the UI needs. Pure functions, so the mapping is tested without a server.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def events_for(node: str, update: Any) -> Iterator[tuple[str, dict]]:
    if node == "__interrupt__":
        for interrupt in update:
            yield "review", dict(interrupt.value)
        return
    if not isinstance(update, dict):
        return
    if node == "resolve_bike":
        bike = update.get("bike")
        yield (
            "bike",
            {
                "bike_id": bike.id if bike else None,
                "name": f"{bike.year} {bike.make} {bike.model}" if bike else None,
                "note": update.get("bike_note"),
                "question": update.get("bike_question"),
            },
        )
    elif node == "triage_row":
        for row_id, assessment in (update.get("assessments") or {}).items():
            yield "row", {"row_id": row_id, **assessment.model_dump(mode="json")}
        for row_id, error in (update.get("failed_rows") or {}).items():
            yield "row_failed", {"row_id": row_id, "error": error}
    elif node == "route":
        yield (
            "route",
            {
                "outcome": update.get("outcome"),
                "escalated": update.get("escalated", False),
                "escalation_message": update.get("escalation_message"),
                "questions": update.get("questions") or {},
            },
        )
    elif node == "draft":
        draft = update.get("draft") or {}
        yield (
            "draft",
            {
                "work_order_id": update.get("work_order_id"),
                "estimate_total": draft.get("estimate_total"),
                "unverified_parts": draft.get("unverified_parts", []),
                "error": update.get("draft_error"),
            },
        )
