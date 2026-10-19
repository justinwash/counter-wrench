"""lookup_bike: resolve a free-text bike description against the catalog.

Deterministic token matching, not an LLM or embeddings: with a small catalog it's exact and
explainable. Ambiguity is a result, not an error ("Marlin 7" matches two years), which gives
the agent a legitimate reason to ask the customer a question instead of guessing.
"""

from __future__ import annotations

import re
from typing import Literal

import psycopg
from psycopg.rows import dict_row
from pydantic import BaseModel

from counterwrench.catalog import BikeSpec
from counterwrench.rag.chunks import bike_chunks


class BikeSummary(BaseModel):
    bike_id: str
    name: str
    specs: str  # same text as the bike's spec-sheet chunk, wheel sizes with both names


class BikeCandidate(BaseModel):
    bike_id: str
    name: str


class LookupBikeResult(BaseModel):
    status: Literal["found", "ambiguous", "not_found"]
    message: str
    bike: BikeSummary | None = None
    candidates: list[BikeCandidate] = []


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _name(bike: BikeSpec) -> str:
    return f"{bike.year} {bike.make} {bike.model}"


def load_bikes(conn: psycopg.Connection) -> list[BikeSpec]:
    rows = conn.cursor(row_factory=dict_row).execute("SELECT * FROM bikes ORDER BY id").fetchall()
    return [BikeSpec.model_validate(row) for row in rows]


def summarize(bike: BikeSpec) -> BikeSummary:
    return BikeSummary(bike_id=bike.id, name=_name(bike), specs=bike_chunks([bike])[0].content)


def match_bikes(description: str, bikes: list[BikeSpec]) -> LookupBikeResult:
    """Score each bike by how many description words appear in its make, model and year.
    Words no bike uses (colors, "maybe") are ignored. A match needs at least one model word:
    "Trek" alone is too vague."""
    words = set(_tokens(description))
    best: list[BikeSpec] = []
    best_score = 0
    for bike in bikes:
        model_words = set(_tokens(bike.model))
        all_words = model_words | set(_tokens(bike.make)) | {str(bike.year)}
        if not words & model_words:
            continue
        score = len(words & all_words)
        if score > best_score:
            best, best_score = [bike], score
        elif score == best_score:
            best.append(bike)

    if not best:
        return LookupBikeResult(
            status="not_found",
            message=(
                f"No catalog bike matches {description!r}. Treat the bike as unknown: don't "
                "quote parts; ask for make, model and year, or a photo."
            ),
        )
    if len(best) == 1:
        return LookupBikeResult(
            status="found", message=f"Matched {_name(best[0])}.", bike=summarize(best[0])
        )
    return LookupBikeResult(
        status="ambiguous",
        message=(
            f"{description!r} matches {len(best)} catalog bikes with different specs. "
            "Ask the customer which one (usually the model year) before quoting parts."
        ),
        candidates=[BikeCandidate(bike_id=b.id, name=_name(b)) for b in best],
    )


def lookup_bike(conn: psycopg.Connection, description: str) -> LookupBikeResult:
    return match_bikes(description, load_bikes(conn))
