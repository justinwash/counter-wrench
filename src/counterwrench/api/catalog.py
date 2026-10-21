"""Picklists for the intake screen: complaints with their allowed areas, and bike search."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from counterwrench.agent.prompt_builder import label
from counterwrench.taxonomy import Complaint, allowed_areas
from counterwrench.tools.bikes import BikeCandidate, load_bikes

router = APIRouter(tags=["catalog"])


class Option(BaseModel):
    value: str
    label: str


class ComplaintOption(Option):
    areas: list[Option]  # the suspected areas staff may pick for this complaint


@router.get("/taxonomy")
def taxonomy() -> list[ComplaintOption]:
    return [
        ComplaintOption(
            value=c.value, label=label(c.value),
            areas=[Option(value=a.value, label=label(a.value))
                   for a in sorted(allowed_areas(c), key=lambda a: (a.value == "unsure", a.value))],
        )
        for c in Complaint
    ]  # fmt: skip


class LaborOption(BaseModel):
    code: str
    name: str
    price_cents: int
    category: str


@router.get("/labor-menu")
def labor_menu(request: Request) -> list[LaborOption]:
    with request.app.state.cw.deps.connect() as conn:
        rows = conn.execute(
            "SELECT code, name, price_cents, category FROM labor_menu ORDER BY category, name"
        ).fetchall()
    return [LaborOption(code=c, name=n, price_cents=p, category=cat) for c, n, p, cat in rows]


@router.get("/bikes")
def bikes(request: Request, q: str = "") -> list[BikeCandidate]:
    """Catalog bikes whose make, model and year contain every word of `q`."""
    words = q.lower().split()
    with request.app.state.cw.deps.connect() as conn:
        found = load_bikes(conn)
    out = []
    for bike in found:
        name = f"{bike.year} {bike.make} {bike.model}"
        if all(w in name.lower() for w in words):
            out.append(BikeCandidate(bike_id=bike.id, name=name))
    return sorted(out, key=lambda b: b.name)
