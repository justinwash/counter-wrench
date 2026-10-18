import re

import pytest
from pydantic import ValidationError

from counterwrench.db.migrate import migrate
from counterwrench.models import (
    BikeCategory,
    BrakeType,
    CompatResult,
    IntakeForm,
    LaborLine,
    PartCategory,
    PartLine,
    RotorMount,
    RowAssessment,
    Severity,
    TriageResult,
    WorkOrderDraft,
    max_severity,
)
from counterwrench.taxonomy import Complaint, SuspectedArea, allowed_areas, is_allowed, pairs

# --- Taxonomy -------------------------------------------------------------------------------


def test_every_complaint_has_areas():
    for complaint in Complaint:
        assert len(allowed_areas(complaint)) >= 2  # at least one real area plus unsure


def test_unsure_always_allowed():
    assert all(is_allowed(c, SuspectedArea.UNSURE) for c in Complaint)


def test_other_allows_everything():
    assert allowed_areas(Complaint.OTHER) == frozenset(SuspectedArea)


def test_every_area_is_reachable_from_a_specific_complaint():
    specific = set().union(*(allowed_areas(c) for c in Complaint if c is not Complaint.OTHER))
    assert specific == set(SuspectedArea)


@pytest.mark.parametrize(
    ("complaint", "area"),
    [
        (Complaint.CREAK, SuspectedArea.FRAME),  # cracked frames creak
        (Complaint.SUSPENSION_KNOCK, SuspectedArea.HEADSET),  # loose headset feels like fork knock
        (Complaint.SUSPENSION_PACKING_UP, SuspectedArea.SUSPENSION_SETUP),  # often just rebound
    ],
)
def test_deliberate_cross_area_options(complaint, area):
    assert is_allowed(complaint, area)


def test_disallowed_pair():
    assert not is_allowed(Complaint.FLAT_TIRE, SuspectedArea.BOTTOM_BRACKET)


def test_pairs_are_unique_and_sorted():
    rows = pairs()
    assert rows == sorted(set(rows))


# --- Intake form ---------------------------------------------------------------------------

ROW = {"row_id": "r1", "complaint": "creak", "suspected_area": "bottom_bracket"}


def intake(**overrides):
    return IntakeForm.model_validate({"bike_id": "trek-fuel-ex-8-2024", "rows": [ROW], **overrides})


def test_valid_intake():
    form = intake(answers={"r1": "Only when standing"})
    assert form.rows[0].complaint is Complaint.CREAK


def test_freetext_bike_instead_of_catalog():
    form = intake(bike_id=None, bike_freetext="Old blue Specialized, maybe 2015")
    assert form.bike_id is None


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"bike_id": None}, "exactly one"),
        ({"bike_freetext": "also this"}, "exactly one"),
        ({"rows": []}, "at least 1"),
        ({"rows": [ROW, ROW]}, "unique"),
        ({"answers": {"r9": "yes"}}, "don't exist"),
        ({"rows": [{**ROW, "suspected_area": "tube"}]}, "isn't an option"),
        ({"rows": [{**ROW, "complaint": "explodes"}]}, "complaint"),
        ({"rows": [{**ROW, "note": "x" * 501}]}, "at most 500"),
        ({"bike_id": "Trek Fuel EX"}, "pattern"),
        ({"surprise": True}, "Extra inputs"),
    ],
)
def test_invalid_intake(overrides, message):
    with pytest.raises(ValidationError, match=message):
        intake(**overrides)


def test_blank_note_is_rejected_not_stored():
    with pytest.raises(ValidationError):
        intake(rows=[{**ROW, "note": "   "}])


def test_intake_json_schema_exposes_picklists():
    schema = IntakeForm.model_json_schema()
    assert set(schema["$defs"]["Complaint"]["enum"]) == {c.value for c in Complaint}
    assert set(schema["$defs"]["SuspectedArea"]["enum"]) == {a.value for a in SuspectedArea}


# --- Assessment and triage ------------------------------------------------------------------

ASSESSMENT = {
    "row_id": "r1",
    "severity": "needs_service",
    "likely_causes": ["Dry seatpost"],
    "agrees_with_suspected_area": False,
    "disagreement_reason": "Creaks only when seated, which points to the seatpost.",
    "suggested_labor": ["SEATPOST-SERVICE"],
}


def test_valid_assessment():
    assert RowAssessment.model_validate(ASSESSMENT).severity is Severity.NEEDS_SERVICE


@pytest.mark.parametrize(
    "overrides",
    [
        {"disagreement_reason": None},  # disagreeing without a reason
        {"agrees_with_suspected_area": True},  # agreeing but still giving a reason
        {"likely_causes": []},
        {"suggested_labor": ["seatpost service"]},  # not a labor code
        {"suggested_part_categories": ["frame"]},  # not a part category
    ],
)
def test_invalid_assessment(overrides):
    with pytest.raises(ValidationError):
        RowAssessment.model_validate({**ASSESSMENT, **overrides})


def test_overall_severity_is_the_worst_row():
    agree = {**ASSESSMENT, "agrees_with_suspected_area": True, "disagreement_reason": None}
    result = TriageResult(
        assessments=[
            RowAssessment.model_validate(
                {**agree, "row_id": "r1", "severity": "cosmetic_or_adjustment"}
            ),
            RowAssessment.model_validate({**agree, "row_id": "r2", "severity": "safety_critical"}),
        ]
    )
    assert result.overall_severity is Severity.SAFETY_CRITICAL
    assert result.escalated


def test_max_severity_ordering():
    assert max_severity([Severity.NEEDS_SERVICE, Severity.COSMETIC_OR_ADJUSTMENT]) is (
        Severity.NEEDS_SERVICE
    )


# --- Compat and work order ------------------------------------------------------------------


def test_incompatible_part_cannot_need_adapter():
    with pytest.raises(ValidationError):
        CompatResult(
            part_id="sram-xg-1275", compatible=False, reasons=["XD only"], requires_adapter="x"
        )


def test_estimate_total_is_computed_not_supplied():
    draft = WorkOrderDraft(
        severity="needs_service",
        labor_lines=[LaborLine(code="BB-INSTALL", qty=1, unit_price_cents=4500)],
        part_lines=[PartLine(part_id="shimano-bb-mt800", qty=1, unit_price_cents=3499)],
        customer_explanation="Your bottom bracket bearings are worn.",
    )
    assert draft.estimate_total_cents == 7999
    with pytest.raises(ValidationError, match="Extra inputs"):
        WorkOrderDraft.model_validate({**draft.model_dump(), "estimate_total_cents": 1})


def test_work_order_json_schema():
    schema = WorkOrderDraft.model_json_schema(mode="serialization")
    assert "estimate_total_cents" in schema["properties"]


# --- Python enums match the SQL CHECK constraints ----------------------------------------------


def check_values(conn, table: str, column: str) -> set[str]:
    """Values allowed by the `column = ANY (ARRAY[...])` CHECK constraint on `table`."""
    rows = conn.execute(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conrelid = %s::regclass AND contype = 'c'",
        (table,),
    ).fetchall()
    for (definition,) in rows:
        if re.search(rf"\(\(?{column} = ANY", definition):
            return set(re.findall(r"'([^']+)'::text", definition))
    raise AssertionError(f"no list CHECK on {table}.{column}")


@pytest.mark.parametrize(
    ("table", "column", "enum"),
    [
        ("bikes", "category", BikeCategory),
        ("bikes", "brake_type", BrakeType),
        ("bikes", "rotor_mount", RotorMount),
        ("parts", "category", PartCategory),
    ],
)
def test_python_enum_matches_sql_check(conn, table, column, enum):
    migrate(conn)
    assert check_values(conn, table, column) == {member.value for member in enum}
