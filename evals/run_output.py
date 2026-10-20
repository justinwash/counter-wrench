"""The shape of one agent run, as the evaluators see it.

The step-15 runner turns each graph run (final state plus the saved work order) into a
RunOutput. Evaluators read only this and the dataset's labels, so they're pure functions that
can be unit-tested with hand-built outputs: no model calls, no database, no LangSmith.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AssessmentOut(BaseModel):
    row_id: str
    severity: str
    agrees: bool | None
    likely_causes: list[str] = Field(default_factory=list)
    disagreement_reason: str | None = None
    question: str | None = None
    suggested_labor: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)


class ChunkOut(BaseModel):
    """A knowledge chunk retrieved for a row: what the agent saw, so the judge can see it too."""

    chunk_id: str
    heading: str
    content: str


class LineOut(BaseModel):
    kind: Literal["labor", "part"]
    code: str | None = None  # labor lines
    part_id: str | None = None  # part lines
    qty: int = 1
    unit_price_cents: int
    position: str | None = None
    unverified: bool = False
    unverified_reason: str | None = None


class DraftOut(BaseModel):
    work_order_id: int
    status: str
    severity: str
    priority: bool
    estimate_total_cents: int
    lines: list[LineOut] = Field(default_factory=list)
    customer_explanation: str = ""
    mechanic_notes: str | None = None
    stored_intake: dict | None = None  # the intake as saved with the order

    def labor_codes(self) -> list[str]:
        return [line.code for line in self.lines if line.kind == "labor" and line.code]

    def part_lines(self) -> list[LineOut]:
        return [line for line in self.lines if line.kind == "part"]


class ToolCall(BaseModel):
    tool: str
    args: dict = Field(default_factory=dict)


class RunOutput(BaseModel):
    bike_id: str | None  # the bike the graph resolved, if any
    assessments: dict[str, AssessmentOut] = Field(default_factory=dict)
    row_chunks: dict[str, list[ChunkOut]] = Field(default_factory=dict)
    failed_rows: list[str] = Field(default_factory=list)
    escalated: bool = False
    questions: dict[str, str] = Field(default_factory=dict)  # row id or "bike" -> question
    outcome: str
    draft: DraftOut | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    triage_retries: int = 0
