"""find_compatible_parts: the compatibility engine, shaped for the agent.

Compatible parts are listed; unknown ones are listed separately and labeled unverified so the
model can't miss it; incompatible parts are left out (so the model never sees a wrong part it
could pick up), with a count and the main reasons.
"""

from __future__ import annotations

from collections import Counter

import psycopg
from pydantic import BaseModel

from counterwrench.compat.lookup import find_compatible_parts as _find
from counterwrench.compat.lookup import load_parts
from counterwrench.models import CompatStatus, PartCategory

UNVERIFIED_LABEL = "UNVERIFIED: mechanic to confirm. Never tell the customer this fits."


class PartFit(BaseModel):
    part_id: str
    name: str
    price: str
    position: str | None = None  # front/rear for tires, tubes, rotors
    why: str
    adapter: str | None = None


class CompatiblePartsResult(BaseModel):
    bike_id: str
    category: str
    compatible: list[PartFit] = []
    unverified: list[PartFit] = []
    unverified_note: str | None = None
    omitted_incompatible: int = 0
    omitted_reasons: list[str] = []
    error: str | None = None


def find_compatible_parts(
    conn: psycopg.Connection, bike_id: str, category: str, tire_width_mm: int | None = None
) -> CompatiblePartsResult:
    try:
        part_category = PartCategory(category)
    except ValueError:
        valid = ", ".join(c.value for c in PartCategory)
        return CompatiblePartsResult(
            bike_id=bike_id, category=category, error=f"Unknown category; use one of: {valid}."
        )
    try:
        results = _find(conn, bike_id, part_category, tire_width_mm)
    except LookupError:
        return CompatiblePartsResult(
            bike_id=bike_id,
            category=category,
            error=f"No catalog bike with id {bike_id!r}. Resolve the bike with lookup_bike first.",
        )

    parts = {p.id: p for p in load_parts(conn, part_category)}
    result = CompatiblePartsResult(bike_id=bike_id, category=category)
    omitted = Counter()
    for r in results:
        part = parts[r.part_id]
        fit = PartFit(
            part_id=r.part_id,
            name=f"{part.brand} {part.name}",
            price=f"${part.price_cents / 100:.2f}",
            position=r.position,
            why=r.reasons[0],
            adapter=r.requires_adapter,
        )
        if r.status is CompatStatus.COMPATIBLE:
            result.compatible.append(fit)
        elif r.status is CompatStatus.UNKNOWN:
            result.unverified.append(fit)
        else:
            omitted[r.reasons[0]] += 1
    if result.unverified:
        result.unverified_note = UNVERIFIED_LABEL
    result.omitted_incompatible = sum(omitted.values())
    result.omitted_reasons = [reason for reason, _ in omitted.most_common(3)]
    return result
