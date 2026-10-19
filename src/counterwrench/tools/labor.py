"""Service menu tools: exact lookup by code, and search by description."""

from __future__ import annotations

import psycopg
from psycopg.rows import dict_row
from pydantic import BaseModel


class LaborInfo(BaseModel):
    code: str
    name: str
    price: str
    est_minutes: int
    includes: str
    category: str


class LaborLookupResult(BaseModel):
    item: LaborInfo | None = None
    error: str | None = None


class LaborSearchResult(BaseModel):
    items: list[LaborInfo] = []
    note: str | None = None


def _info(row: dict) -> LaborInfo:
    return LaborInfo(
        code=row["code"],
        name=row["name"],
        price=f"${row['price_cents'] / 100:.2f}",
        est_minutes=row["est_minutes"],
        includes=row["description"],
        category=row["category"],
    )


def get_labor_item(conn: psycopg.Connection, code: str) -> LaborLookupResult:
    row = (
        conn.cursor(row_factory=dict_row)
        .execute("SELECT * FROM labor_menu WHERE code = %s", (code.strip().upper(),))
        .fetchone()
    )
    if row is None:
        return LaborLookupResult(
            error=f"No labor code {code!r}. Use search_labor_menu to find the right one; "
            "never invent codes."
        )
    return LaborLookupResult(item=_info(row))


def search_labor_menu(conn: psycopg.Connection, query: str, k: int = 5) -> LaborSearchResult:
    """Full-text match on code, name and description; any query word can match (OR)."""
    rows = (
        conn.cursor(row_factory=dict_row)
        .execute(
            """
            WITH q AS (
                SELECT NULLIF(replace(plainto_tsquery('english', %(q)s)::text, '&', '|'), '')
                       AS text
            ), menu AS (
                SELECT *, to_tsvector('english', replace(code, '-', ' ') || ' ' || name || ' '
                                      || description) AS tsv
                FROM labor_menu
            )
            SELECT menu.* FROM menu, q
            WHERE q.text IS NOT NULL AND tsv @@ to_tsquery('english', q.text)
            ORDER BY ts_rank_cd(tsv, to_tsquery('english', q.text)) DESC, code
            LIMIT %(k)s
            """,
            {"q": query, "k": k},
        )
        .fetchall()
    )
    if not rows:
        return LaborSearchResult(note=f"No service menu items match {query!r}.")
    return LaborSearchResult(items=[_info(r) for r in rows])
