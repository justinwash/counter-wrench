"""draft_work_order: the agent's only write.

The agent proposes lines; code validates every one, prices it from the catalog and totals it
(D-012), then saves the draft as awaiting_review. All or nothing: any problem rejects the whole
draft, writes nothing, and tells the agent exactly what to fix so it can retry.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from counterwrench.compat.engine import PER_WHEEL, check
from counterwrench.compat.lookup import load_bike, load_part, load_rules
from counterwrench.models import (
    CompatStatus,
    LaborLine,
    PartCategory,
    PartLine,
    Severity,
    WheelPosition,
    WorkOrderDraft,
    WorkOrderStatus,
)

# --- What the model may propose: codes, parts and quantities, never prices -------------------


class LaborRequest(BaseModel):
    code: str = Field(description="Service menu code from get_labor_item or search_labor_menu.")
    qty: int = Field(default=1, ge=1, le=10, description="Units, e.g. 2 for both brakes.")


class PartRequest(BaseModel):
    part_id: str = Field(description="A part_id from find_compatible_parts.")
    qty: int = Field(default=1, ge=1, le=10)
    position: Literal["front", "rear"] | None = Field(
        default=None, description="Required for tires, tubes and rotors."
    )
    tire_width_mm: int | None = Field(default=None, description="Installed tire width, for tubes.")


class DraftWorkOrderArgs(BaseModel):
    bike_id: str | None = Field(default=None, description="Catalog bike id, if known.")
    bike_freetext: str | None = Field(
        default=None, description="The customer's description, when the bike isn't in the catalog."
    )
    severity: Severity
    labor_lines: list[LaborRequest] = Field(default_factory=list)
    part_lines: list[PartRequest] = Field(default_factory=list)
    customer_explanation: str = Field(
        description="Plain-language explanation for the customer: what we found and why."
    )
    mechanic_notes: str | None = Field(default=None, description="Notes for the mechanic.")
    citations: list[str] = Field(
        default_factory=list, description="chunk_ids from search_knowledge that support this."
    )


# Shop rules for a coherent order (F-009): every part has the labor that fits it, and nothing
# works on a part that's being replaced. evals/evaluators/draft.py checks the saved orders
# against its own copy of these rules, so a bug here can't hide from the evals.
INSTALL_LABOR: dict[str, set[str]] = {
    "cassette": {"CASSETTE-INSTALL"},
    "chain": {"CHAIN-INSTALL"},
    "rear_derailleur": {"DERAILLEUR-INSTALL"},
    "brake_pads": {"BRAKE-PAD-INSTALL"},
    "rotor": {"ROTOR-INSTALL"},
    "bottom_bracket": {"BB-INSTALL-THREADED", "BB-INSTALL-PRESSFIT"},
    "tire": {"TIRE-INSTALL", "TUBELESS-SETUP"},
    "tube": {"FLAT-REPAIR", "TIRE-INSTALL"},
}
WORKS_ON: dict[str, str] = {"ROTOR-TRUE": "rotor"}  # labor code -> the part it adjusts


def coherence_problems(categories: dict[str, str], codes: set[str]) -> list[str]:
    """`categories` maps each drafted part_id to its category."""
    problems = []
    for part_id, category in categories.items():
        options = INSTALL_LABOR.get(category, set())
        if options and not codes & options:
            problems.append(
                f"{part_id}: add the labor that fits it ({' or '.join(sorted(options))})."
            )
    replaced = set(categories.values())
    for code in sorted(codes):
        if WORKS_ON.get(code) in replaced:
            problems.append(f"{code} works on a {WORKS_ON[code]} that's being replaced; remove it.")
    return problems


class DraftResult(BaseModel):
    status: Literal["saved", "rejected"]
    work_order_id: int | None = None
    work_order_status: str | None = None
    estimate_total: str | None = None
    unverified_parts: list[str] = []
    problems: list[str] = []
    message: str


def _validate(
    conn: psycopg.Connection, args: DraftWorkOrderArgs
) -> tuple[WorkOrderDraft | None, list[str]]:
    problems: list[str] = []
    bike = None
    if args.bike_id:
        bike = load_bike(conn, args.bike_id)
        if bike is None:
            problems.append(f"No catalog bike {args.bike_id!r}; resolve it with lookup_bike.")
    elif not args.bike_freetext:
        problems.append("Give bike_id (catalog) or bike_freetext (not in the catalog).")

    cursor = conn.cursor(row_factory=dict_row)
    labor_lines = []
    for req in args.labor_lines:
        code = req.code.strip().upper()
        row = cursor.execute(
            "SELECT price_cents FROM labor_menu WHERE code = %s", (code,)
        ).fetchone()
        if row is None:
            problems.append(f"Unknown labor code {req.code!r}; use search_labor_menu.")
            continue
        labor_lines.append(LaborLine(code=code, qty=req.qty, unit_price_cents=row["price_cents"]))

    part_lines = []
    categories: dict[str, str] = {}
    if args.part_lines and bike is None:
        problems.append(
            "Parts need a catalog bike so the compatibility engine can check them. For a bike "
            "not in the catalog, leave parts off; use labor lines and mechanic notes."
        )
    elif args.part_lines:
        rules = load_rules(conn)
        for req in args.part_lines:
            part = load_part(conn, req.part_id)
            if part is None:
                problems.append(f"Unknown part {req.part_id!r}; use find_compatible_parts.")
                continue
            per_wheel = PartCategory(part.category) in PER_WHEEL
            if per_wheel and req.position is None:
                problems.append(f"{req.part_id}: say which wheel (position front or rear).")
                continue
            position = WheelPosition(req.position) if per_wheel else None
            result = check(bike, part, rules, position, req.tire_width_mm)
            if result.status is CompatStatus.INCOMPATIBLE:
                where = f" ({position})" if position else ""
                problems.append(f"{req.part_id}{where} doesn't fit: {result.reasons[0]}")
                continue
            unverified = result.status is CompatStatus.UNKNOWN
            categories[part.id] = str(part.category)
            part_lines.append(
                PartLine(
                    part_id=part.id, qty=req.qty, unit_price_cents=part.price_cents,
                    position=position, unverified=unverified,
                    unverified_reason=result.reasons[0] if unverified else None,
                )
            )  # fmt: skip

    if not problems:
        problems = coherence_problems(categories, {line.code for line in labor_lines})
    if problems:
        return None, problems
    draft = WorkOrderDraft(
        bike_id=args.bike_id,
        bike_freetext=args.bike_freetext,
        severity=args.severity,
        labor_lines=labor_lines,
        part_lines=part_lines,
        customer_explanation=args.customer_explanation,
        mechanic_notes=args.mechanic_notes,
        citations=args.citations,
    )
    return draft, []


def _insert_lines(conn: psycopg.Connection, order_id: int, draft: WorkOrderDraft) -> None:
    for line in draft.labor_lines:
        conn.execute(
            "INSERT INTO work_order_lines (work_order_id, labor_code, qty, unit_price_cents) "
            "VALUES (%s, %s, %s, %s)",
            (order_id, line.code, line.qty, line.unit_price_cents),
        )
    for line in draft.part_lines:
        conn.execute(
            "INSERT INTO work_order_lines (work_order_id, part_id, qty, unit_price_cents, "
            "position, unverified, unverified_reason) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (
                order_id, line.part_id, line.qty, line.unit_price_cents,
                line.position.value if line.position else None, line.unverified,
                line.unverified_reason,
            ),
        )  # fmt: skip


class EditLinesArgs(BaseModel):
    """A mechanic's replacement lines for a draft awaiting review."""

    editor: str = Field(min_length=1)
    labor_lines: list[LaborRequest] = Field(default_factory=list)
    part_lines: list[PartRequest] = Field(default_factory=list)


def edit_lines(conn: psycopg.Connection, order_id: int, edit: EditLinesArgs) -> list[str]:
    """Replace a draft's lines, validated exactly like the agent's (fit, catalog prices,
    coherence). Returns the problems; nothing changes unless there are none."""
    order = conn.execute(
        "SELECT bike_id, bike_freetext, severity, customer_explanation, mechanic_notes, citations "
        "FROM work_orders WHERE id = %s AND status = 'awaiting_review'",
        (order_id,),
    ).fetchone()
    if order is None:
        return [f"Work order {order_id} isn't awaiting review."]
    bike_id, freetext, severity, explanation, notes, citations = order
    args = DraftWorkOrderArgs(
        bike_id=bike_id, bike_freetext=freetext, severity=severity,
        labor_lines=edit.labor_lines, part_lines=edit.part_lines,
        customer_explanation=explanation, mechanic_notes=notes, citations=citations,
    )  # fmt: skip
    draft, problems = _validate(conn, args)
    if draft is None:
        return problems
    with conn.transaction():
        conn.execute("DELETE FROM work_order_lines WHERE work_order_id = %s", (order_id,))
        _insert_lines(conn, order_id, draft)
        conn.execute(
            "UPDATE work_orders SET estimate_total_cents = %s, edited_by = %s, edited_at = now() "
            "WHERE id = %s",
            (draft.estimate_total_cents, edit.editor, order_id),
        )
    return []


def record_decline(
    conn: psycopg.Connection,
    *,
    intake: dict,
    bike_id: str | None,
    bike_freetext: str | None,
    severity: str,
    staff: str,
    waiver_signed: bool,
    langsmith_run_id: UUID | None,
    source: str,
) -> int:
    """Keep the customer's decline as a record (no lines, nothing to approve). The database
    refuses a safety-critical decline without a signed waiver."""
    waiver = " Signed a waiver of liability." if waiver_signed else ""
    advised = " We advised against riding it." if severity == "safety_critical" else ""
    note = f"Customer declined the recommended service.{advised}{waiver} Bike released."
    return conn.execute(
        """
        INSERT INTO work_orders (status, bike_id, bike_freetext, severity, customer_explanation,
            estimate_total_cents, intake, langsmith_run_id, source, reviewed_by, reviewed_at,
            review_notes, waiver_signed)
        VALUES ('declined', %s, %s, %s, %s, 0, %s, %s, %s, %s, now(), %s, %s) RETURNING id
        """,
        (bike_id, bike_freetext, severity, note, Jsonb(intake), langsmith_run_id, source, staff,
         note, waiver_signed),
    ).fetchone()[0]  # fmt: skip


def draft_work_order(
    conn: psycopg.Connection,
    args: DraftWorkOrderArgs,
    intake: dict | None = None,
    langsmith_run_id: UUID | None = None,
    source: str = "counter",
) -> DraftResult:
    draft, problems = _validate(conn, args)
    if draft is None:
        return DraftResult(
            status="rejected",
            problems=problems,
            message="Nothing was saved. Fix the problems listed and call draft_work_order again.",
        )
    with conn.transaction():
        # Status is hard-coded: an agent draft can only ever await review.
        order_id = conn.execute(
            """
            INSERT INTO work_orders (status, bike_id, bike_freetext, severity,
                customer_explanation, mechanic_notes, citations, estimate_total_cents,
                intake, langsmith_run_id, source)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
            """,
            (
                WorkOrderStatus.AWAITING_REVIEW.value, draft.bike_id, draft.bike_freetext,
                draft.severity.value, draft.customer_explanation, draft.mechanic_notes,
                draft.citations, draft.estimate_total_cents,
                Jsonb(intake) if intake is not None else None, langsmith_run_id, source,
            ),
        ).fetchone()[0]  # fmt: skip
        _insert_lines(conn, order_id, draft)
    unverified = [line.part_id for line in draft.part_lines if line.unverified]
    note = " Unverified parts are flagged for the mechanic." if unverified else ""
    return DraftResult(
        status="saved",
        work_order_id=order_id,
        work_order_status=WorkOrderStatus.AWAITING_REVIEW.value,
        estimate_total=f"${draft.estimate_total_cents / 100:.2f}",
        unverified_parts=unverified,
        message=f"Draft saved for mechanic review; prices and total come from the catalog.{note}",
    )
