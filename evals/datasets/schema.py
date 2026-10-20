"""Eval example schemas, loading, and validation against the real catalog and knowledge base.

Labels come from Justin. Only examples with `labeled_by: justin` are uploaded, so a label
drafted by the assistant can never reach the eval set by accident: if the same model family
writes both the cases and the answers, the evals mostly measure agreement between LLMs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Self

import yaml
from pydantic import Field, model_validator

from counterwrench.models import IntakeForm, LaborCode, PartCategory, Severity, Slug, Strict

DATASETS_DIR = Path(__file__).parent
E2E_DIR = DATASETS_DIR / "e2e"
RETRIEVAL_FILE = DATASETS_DIR / "retrieval.yaml"

Slice = Literal[
    "normal",
    "edge",
    "staff_misattribution",
    "note_contradicts_picklist",
    "safety",
    "adversarial",
]
Author = Literal["justin", "assistant"]


class RowExpectation(Strict):
    """What a correct assessment of one intake row looks like."""

    severity: Severity
    # true/false, or null when staff picked "unsure" (agreement doesn't apply).
    agrees: bool | None
    # False when agreement can't be judged at the counter (needs an inspection first).
    agreement_scored: bool = True
    question_expected: bool = False
    # Labor is a range, not one answer: shops reasonably differ on extras like SAFETY-CHECK.
    labor_required: list[LaborCode] = Field(default_factory=list)
    labor_acceptable: list[LaborCode] = Field(default_factory=list)
    labor_forbidden: list[LaborCode] = Field(default_factory=list)
    # Expected part categories; empty means no parts (e.g. an adjustment).
    part_categories: list[PartCategory] = Field(default_factory=list)
    forbidden_parts: list[Slug] = Field(default_factory=list)

    @model_validator(mode="after")
    def _labor_sets_disjoint(self) -> Self:
        allowed = set(self.labor_required) | set(self.labor_acceptable)
        clash = allowed & set(self.labor_forbidden)
        if clash:
            raise ValueError(f"labor codes both allowed and forbidden: {sorted(clash)}")
        return self


class E2EExample(Strict):
    id: Slug
    slice: Slice
    tags: list[str] = Field(default_factory=list)  # e.g. category:brakes, mullet, d-017
    author: Author  # who wrote the intake
    labeled_by: Literal["justin"] | None = None  # None = drafted, not yet labeled
    intake: IntakeForm
    rows: dict[str, RowExpectation]
    bike_question_expected: bool = False
    order_expected: bool  # false when the run should stop for answers
    judge_notes: str | None = None

    @model_validator(mode="after")
    def _rows_match_intake(self) -> Self:
        intake_rows = {row.row_id for row in self.intake.rows}
        if set(self.rows) != intake_rows:
            raise ValueError(
                f"expectations {sorted(self.rows)} != intake rows {sorted(intake_rows)}"
            )
        return self

    @property
    def escalation_required(self) -> bool:
        return any(r.severity is Severity.SAFETY_CRITICAL for r in self.rows.values())


class RetrievalExample(Strict):
    id: Slug
    query: str = Field(min_length=3)
    bike_id: Slug | None = None
    # Any of these counts as a hit: several sections can legitimately answer one question.
    expected_chunks: list[str] = Field(min_length=1)
    author: Author
    labeled_by: Literal["justin"] | None = None
    notes: str | None = None


def _read_list(path: Path) -> list:
    data = yaml.safe_load(path.read_text("utf-8")) or []
    if not isinstance(data, list):
        raise ValueError(f"{path.name}: expected a list of examples")
    return data


def load_e2e(directory: Path = E2E_DIR) -> list[E2EExample]:
    return [
        E2EExample.model_validate(item)
        for path in sorted(directory.glob("*.yaml"))
        for item in _read_list(path)
    ]


def load_retrieval(path: Path = RETRIEVAL_FILE) -> list[RetrievalExample]:
    return [RetrievalExample.model_validate(item) for item in _read_list(path)]


def catalog_problems(
    e2e: list[E2EExample],
    retrieval: list[RetrievalExample],
    *,
    bike_ids: set[str],
    labor_codes: set[str],
    part_ids: set[str],
    chunk_ids: set[str],
) -> list[str]:
    """References that don't exist. A typo in a label would otherwise show up as a silent
    'agent failure' that's really a dataset bug."""
    problems = []
    ids = [e.id for e in e2e] + [r.id for r in retrieval]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        problems.append(f"duplicate example ids: {duplicates}")
    for ex in e2e:
        if ex.intake.bike_id and ex.intake.bike_id not in bike_ids:
            problems.append(f"{ex.id}: unknown bike {ex.intake.bike_id}")
        for row_id, exp in ex.rows.items():
            codes = [*exp.labor_required, *exp.labor_acceptable, *exp.labor_forbidden]
            for code in codes:
                if code not in labor_codes:
                    problems.append(f"{ex.id}/{row_id}: unknown labor code {code}")
            for part in exp.forbidden_parts:
                if part not in part_ids:
                    problems.append(f"{ex.id}/{row_id}: unknown part {part}")
    for ex in retrieval:
        if ex.bike_id and ex.bike_id not in bike_ids:
            problems.append(f"{ex.id}: unknown bike {ex.bike_id}")
        for chunk in ex.expected_chunks:
            if chunk not in chunk_ids:
                problems.append(f"{ex.id}: unknown chunk {chunk}")
    return problems
