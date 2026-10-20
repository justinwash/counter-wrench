"""Draft evaluators: was an order created when expected, and is every line right?

Most return None when no draft exists: `order_created_when_expected` already scores that, so
the line checks don't count the same miss twice.
"""

from __future__ import annotations

import re

from counterwrench.compat.engine import check
from counterwrench.guardrails.pii import CARD, EMAIL, NAME_PATTERNS, PHONE
from counterwrench.models import CompatStatus, WheelPosition
from evals.evaluators import Catalog, Reference, Score
from evals.run_output import RunOutput

# Labor that installs each part category; any one of them covers the part.
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
# Labor that makes no sense alongside replacing the part it works on.
CONFLICTS: dict[str, set[str]] = {"rotor": {"ROTOR-TRUE"}}


def order_created_when_expected(run: RunOutput, ref: Reference, ctx: Catalog) -> Score:
    created = run.draft is not None
    if created == ref.order_expected:
        return Score("order_created_when_expected", 1.0)
    detail = "drafted when it should have stopped" if created else f"no draft ({run.outcome})"
    return Score("order_created_when_expected", 0.0, detail)


def _draft_or_none(key: str, run: RunOutput) -> Score | None:
    return Score(key, None, "no draft") if run.draft is None else None


def labor_required_present(run: RunOutput, ref: Reference, ctx: Catalog) -> Score:
    if skip := _draft_or_none("labor_required_present", run):
        return skip
    required = {code for exp in ref.rows.values() for code in exp.labor_required}
    if not required:
        return Score("labor_required_present", None, "no labor required")
    present = required & set(run.draft.labor_codes())
    missing = sorted(required - present)
    return Score("labor_required_present", len(present) / len(required),
                 f"missing {missing}" if missing else "")  # fmt: skip


def labor_no_extras(run: RunOutput, ref: Reference, ctx: Catalog) -> Score:
    if skip := _draft_or_none("labor_no_extras", run):
        return skip
    allowed = {
        code for exp in ref.rows.values() for code in [*exp.labor_required, *exp.labor_acceptable]
    }
    extras = sorted(set(run.draft.labor_codes()) - allowed)
    return Score(
        "labor_no_extras", 0.0 if extras else 1.0, f"unexpected {extras}" if extras else ""
    )


def labor_forbidden_absent(run: RunOutput, ref: Reference, ctx: Catalog) -> Score:
    if skip := _draft_or_none("labor_forbidden_absent", run):
        return skip
    forbidden = {code for exp in ref.rows.values() for code in exp.labor_forbidden}
    used = sorted(forbidden & set(run.draft.labor_codes()))
    return Score("labor_forbidden_absent", 0.0 if used else 1.0, f"used {used}" if used else "")


def parts_categories_present(run: RunOutput, ref: Reference, ctx: Catalog) -> Score:
    if skip := _draft_or_none("parts_categories_present", run):
        return skip
    expected = {str(c) for exp in ref.rows.values() for c in exp.part_categories}
    if not expected:
        return Score("parts_categories_present", None, "no parts expected")
    drafted = {ctx.parts[line.part_id].category for line in run.draft.part_lines()
               if line.part_id in ctx.parts}  # fmt: skip
    present = expected & drafted
    missing = sorted(expected - present)
    return Score("parts_categories_present", len(present) / len(expected),
                 f"missing {missing}" if missing else "")  # fmt: skip


def forbidden_parts_absent(run: RunOutput, ref: Reference, ctx: Catalog) -> Score:
    if skip := _draft_or_none("forbidden_parts_absent", run):
        return skip
    forbidden = {part for exp in ref.rows.values() for part in exp.forbidden_parts}
    used = sorted(forbidden & {line.part_id for line in run.draft.part_lines()})
    return Score("forbidden_parts_absent", 0.0 if used else 1.0, f"used {used}" if used else "")


def parts_all_compatible(run: RunOutput, ref: Reference, ctx: Catalog) -> Score:
    """Re-check every part line with the compatibility engine, independently of the agent.
    An `unknown` fit passes only when the line is flagged unverified."""
    if skip := _draft_or_none("parts_all_compatible", run):
        return skip
    lines = run.draft.part_lines()
    if not lines:
        return Score("parts_all_compatible", None, "no part lines")
    bike = ctx.bikes.get(run.bike_id or "")
    if bike is None:
        return Score("parts_all_compatible", 0.0, "parts drafted without a catalog bike")
    bad = []
    for line in lines:
        part = ctx.parts.get(line.part_id)
        if part is None:
            bad.append(f"{line.part_id}: not in catalog")
            continue
        position = WheelPosition(line.position) if line.position else None
        try:
            result = check(bike, part, ctx.rules, position)
        except ValueError as exc:
            bad.append(f"{line.part_id}: {exc}")
            continue
        if result.status is CompatStatus.INCOMPATIBLE:
            bad.append(f"{line.part_id}: {result.reasons[0]}")
        elif result.status is CompatStatus.UNKNOWN and not line.unverified:
            bad.append(f"{line.part_id}: fit unknown but not flagged unverified")
    return Score("parts_all_compatible", (len(lines) - len(bad)) / len(lines), "; ".join(bad))


def prices_match_catalog(run: RunOutput, ref: Reference, ctx: Catalog) -> Score:
    """Line prices come from the catalog and the total is their sum (D-012)."""
    if skip := _draft_or_none("prices_match_catalog", run):
        return skip
    problems = []
    for line in run.draft.lines:
        catalog_price = (
            ctx.labor_prices.get(line.code) if line.kind == "labor"
            else getattr(ctx.parts.get(line.part_id), "price_cents", None)
        )  # fmt: skip
        if catalog_price != line.unit_price_cents:
            problems.append(
                f"{line.code or line.part_id}: {line.unit_price_cents} vs catalog {catalog_price}"
            )
    total = sum(line.qty * line.unit_price_cents for line in run.draft.lines)
    if total != run.draft.estimate_total_cents:
        problems.append(f"total {run.draft.estimate_total_cents} != sum of lines {total}")
    return Score("prices_match_catalog", 0.0 if problems else 1.0, "; ".join(problems))


def line_coherence(run: RunOutput, ref: Reference, ctx: Catalog) -> Score:
    """The order makes sense as a whole: parts have labor to install them, and nothing works on
    a part that's being replaced (found in step 10b's live runs)."""
    if skip := _draft_or_none("line_coherence", run):
        return skip
    codes = set(run.draft.labor_codes())
    problems = []
    for line in run.draft.part_lines():
        category = getattr(ctx.parts.get(line.part_id), "category", None)
        if category in INSTALL_LABOR and not (codes & INSTALL_LABOR[category]):
            problems.append(f"{line.part_id}: no install labor")
        clash = codes & CONFLICTS.get(category, set())
        if clash:
            problems.append(f"{sorted(clash)} on a {category} being replaced")
    return Score("line_coherence", 0.0 if problems else 1.0, "; ".join(problems))


def triage_labor_carried(run: RunOutput, ref: Reference, ctx: Catalog) -> Score:
    """Labor triage suggested is on the draft, or the mechanic notes say why not (step 10b
    dropped a headset adjustment silently)."""
    if skip := _draft_or_none("triage_labor_carried", run):
        return skip
    suggested = {code for a in run.assessments.values() for code in a.suggested_labor}
    if not suggested:
        return Score("triage_labor_carried", None, "triage suggested no labor")
    notes = run.draft.mechanic_notes or ""
    dropped = sorted(c for c in suggested - set(run.draft.labor_codes()) if c not in notes)
    return Score("triage_labor_carried", (len(suggested) - len(dropped)) / len(suggested),
                 f"dropped without explanation: {dropped}" if dropped else "")  # fmt: skip


def _pii_in(text: str) -> set[str]:
    found = {m.group() for pattern in (EMAIL, CARD, PHONE) for m in pattern.finditer(text)}
    for pattern in NAME_PATTERNS:
        found |= {m.group(1) for m in pattern.finditer(text)}
    return found


def pii_absent(run: RunOutput, ref: Reference, ctx: Catalog) -> Score:
    """No raw email, phone, card or name from the input reaches anything the run produced."""
    pii = _pii_in(ref.intake.model_dump_json())
    if not pii:
        return Score("pii_absent", None, "no PII in the input")
    produced = run.model_dump_json()
    leaked = sorted(p for p in pii if re.search(re.escape(p), produced))
    return Score(
        "pii_absent", 0.0 if leaked else 1.0, f"{len(leaked)} PII value(s) leaked" if leaked else ""
    )


EVALUATORS = [
    order_created_when_expected, labor_required_present, labor_no_extras, labor_forbidden_absent,
    parts_categories_present, forbidden_parts_absent, parts_all_compatible, prices_match_catalog,
    line_coherence, triage_labor_carried, pii_absent,
]  # fmt: skip
