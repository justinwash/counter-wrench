"""Deterministic and trajectory evaluators. Each takes (run, ref, ctx) and returns a Score.

A score of None means "not applicable to this example" (e.g. draft checks when no draft was
expected), so averages only count examples where the check means something.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache

from counterwrench.catalog import BikeSpec
from counterwrench.compat.engine import Rules
from counterwrench.db.seed import load_seed
from counterwrench.models import IntakeForm
from evals.datasets.schema import RowExpectation


@dataclass(frozen=True)
class Score:
    key: str
    score: float | None
    comment: str = ""


@dataclass(frozen=True)
class Reference:
    """What the dataset says a correct run looks like (one e2e example)."""

    intake: IntakeForm
    rows: dict[str, RowExpectation]
    escalation_required: bool
    bike_question_expected: bool
    order_expected: bool

    @classmethod
    def from_example(cls, example) -> Reference:
        return cls(
            intake=example.intake,
            rows=example.rows,
            escalation_required=example.escalation_required,
            bike_question_expected=example.bike_question_expected,
            order_expected=example.order_expected,
        )


@dataclass(frozen=True)
class Catalog:
    """The catalog as of the run, so evaluators can re-check parts and prices independently."""

    bikes: dict[str, BikeSpec]
    parts: dict[str, object]
    rules: Rules
    labor_prices: dict[str, int]


@cache
def load_catalog() -> Catalog:
    seed = load_seed()
    return Catalog(
        bikes={b.id: BikeSpec.model_validate(b.model_dump(exclude={"source"})) for b in seed.bikes},
        parts={p.id: p for p in seed.parts},
        rules=Rules(seed.compat_rules),
        labor_prices={item.code: item.price_cents for item in seed.labor_menu},
    )
