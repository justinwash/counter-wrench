"""Load catalog data from Postgres and run the engine over it."""

from __future__ import annotations

import psycopg
from psycopg.rows import dict_row
from pydantic import TypeAdapter

from counterwrench.catalog import BikeSpec, CompatRule, Part
from counterwrench.compat.engine import Rules, check_all_positions
from counterwrench.models import CompatResult, CompatStatus, PartCategory

_PARTS = TypeAdapter(list[Part])
_ORDER = {CompatStatus.COMPATIBLE: 0, CompatStatus.UNKNOWN: 1, CompatStatus.INCOMPATIBLE: 2}


def load_bike(conn: psycopg.Connection, bike_id: str) -> BikeSpec | None:
    row = (
        conn.cursor(row_factory=dict_row)
        .execute("SELECT * FROM bikes WHERE id = %s", (bike_id,))
        .fetchone()
    )
    return BikeSpec.model_validate(row) if row else None


def load_parts(conn: psycopg.Connection, category: PartCategory) -> list:
    rows = (
        conn.cursor(row_factory=dict_row)
        .execute(
            "SELECT id, category, brand, name, price_cents, specs FROM parts "
            "WHERE category = %s ORDER BY id",
            (category.value,),
        )
        .fetchall()
    )
    return _PARTS.validate_python(rows)


def load_part(conn: psycopg.Connection, part_id: str):
    row = (
        conn.cursor(row_factory=dict_row)
        .execute(
            "SELECT id, category, brand, name, price_cents, specs FROM parts WHERE id = %s",
            (part_id,),
        )
        .fetchone()
    )
    return _PARTS.validate_python([row])[0] if row else None


def load_rules(conn: psycopg.Connection) -> Rules:
    rows = conn.cursor(row_factory=dict_row).execute("SELECT * FROM compat_rules").fetchall()
    return Rules(CompatRule.model_validate(row) for row in rows)


def find_compatible_parts(
    conn: psycopg.Connection,
    bike_id: str,
    category: PartCategory,
    tire_width_mm: int | None = None,
) -> list[CompatResult]:
    """Every part in the category checked against the bike: compatible first, then unknown,
    then incompatible. Per-wheel parts get one result per wheel."""
    bike = load_bike(conn, bike_id)
    if bike is None:
        raise LookupError(f"No bike with id {bike_id!r}")
    rules = load_rules(conn)
    results = [
        result
        for part in load_parts(conn, category)
        for result in check_all_positions(bike, part, rules, tire_width_mm)
    ]
    return sorted(results, key=lambda r: (_ORDER[r.status], r.position or "", r.part_id))
