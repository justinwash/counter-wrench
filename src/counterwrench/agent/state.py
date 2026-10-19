"""Graph state. Triage branches run in parallel, so the fields they write merge via reducers."""

from __future__ import annotations

import operator
from typing import Annotated, Literal, TypedDict

from counterwrench.catalog import BikeSpec
from counterwrench.models import IntakeForm, RowAssessment
from counterwrench.rag.search import SearchHit


def merge(left: dict, right: dict) -> dict:
    return {**left, **right}


Outcome = Literal["escalated", "needs_answers", "needs_mechanic", "ready_to_draft"]


class GraphState(TypedDict, total=False):
    intake: IntakeForm
    # Resolved catalog bike, or None (free text not found, ambiguous, or unknown id).
    bike: BikeSpec | None
    bike_note: str
    # A question code raises itself, e.g. which Marlin 7 year; no LLM involved.
    bike_question: str | None
    row_chunks: dict[str, list[SearchHit]]
    assessments: Annotated[dict[str, RowAssessment], merge]
    # Rows whose assessment stayed invalid after a retry, with the last error.
    failed_rows: Annotated[dict[str, str], merge]
    triage_retries: Annotated[int, operator.add]
    escalated: bool
    escalation_message: str | None
    questions: dict[str, str]
    outcome: Outcome


class RowTask(TypedDict):
    """What one parallel triage branch receives."""

    intake: IntakeForm
    bike: BikeSpec | None
    row_id: str
    chunks: list[SearchHit]
