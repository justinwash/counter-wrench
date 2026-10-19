"""Core data shapes. The agent, evals, API and UI all depend on these.

`RowAssessment` doubles as the triage step's structured-output schema, so its field
descriptions are written for the LLM: they become part of its instructions.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from typing import Annotated, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    computed_field,
    model_validator,
)

from counterwrench.taxonomy import Complaint, SuspectedArea, is_allowed

# --- Shared types ----------------------------------------------------------------------------

Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")]
LaborCode = Annotated[str, StringConstraints(pattern=r"^[A-Z0-9]+(-[A-Z0-9]+)*$")]
RowId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,20}$")]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class Strict(BaseModel):
    """Reject unknown fields: a typo in a dataset or API payload should fail, not vanish."""

    model_config = ConfigDict(extra="forbid")


# --- Enums mirrored by SQL CHECK constraints (a test keeps them in sync) -------------------


class BikeCategory(StrEnum):
    ROAD = "road"
    GRAVEL = "gravel"
    MTB = "mtb"
    COMMUTER = "commuter"


class BrakeType(StrEnum):
    RIM = "rim"
    MECH_DISC = "mech_disc"
    HYDRAULIC_DISC = "hydraulic_disc"


class RotorMount(StrEnum):
    SIX_BOLT = "6-bolt"
    CENTERLOCK = "centerlock"


class PartCategory(StrEnum):
    CASSETTE = "cassette"
    CHAIN = "chain"
    REAR_DERAILLEUR = "rear_derailleur"
    BRAKE_PADS = "brake_pads"
    ROTOR = "rotor"
    BOTTOM_BRACKET = "bottom_bracket"
    TIRE = "tire"
    TUBE = "tube"


# --- Severity --------------------------------------------------------------------------------


class Severity(StrEnum):
    """One level per distinct counter action, most severe first."""

    SAFETY_CRITICAL = "safety_critical"  # don't ride it; it stays in the shop
    NEEDS_SERVICE = "needs_service"  # book it in
    NEEDS_ADJUSTMENT = "needs_adjustment"  # quick fix, maybe while they wait
    COSMETIC = "cosmetic"  # look it over, confirm it's only cosmetic, hand it back
    NO_ACTION_NEEDED = "no_action_needed"  # working as intended; explain why it's normal

    @property
    def rank(self) -> int:
        return _SEVERITY_RANK[self]


_SEVERITY_RANK = {
    Severity.NO_ACTION_NEEDED: 0,
    Severity.COSMETIC: 1,
    Severity.NEEDS_ADJUSTMENT: 2,
    Severity.NEEDS_SERVICE: 3,
    Severity.SAFETY_CRITICAL: 4,
}


def max_severity(severities: Iterable[Severity]) -> Severity:
    return max(severities, key=lambda s: s.rank)


# --- Intake (what the counter form produces) ---------------------------------------------------


class ComplaintRow(Strict):
    row_id: RowId
    complaint: Complaint
    suspected_area: SuspectedArea
    note: ShortText | None = None

    @model_validator(mode="after")
    def _area_allowed_for_complaint(self) -> Self:
        if not is_allowed(self.complaint, self.suspected_area):
            raise ValueError(
                f"suspected_area '{self.suspected_area}' isn't an option for "
                f"complaint '{self.complaint}'"
            )
        return self


class IntakeForm(Strict):
    bike_id: Slug | None = None
    bike_freetext: ShortText | None = None
    rows: list[ComplaintRow] = Field(min_length=1, max_length=10)
    general_notes: LongText | None = None
    # Staff answers to the agent's per-row questions, keyed by row_id.
    answers: dict[RowId, ShortText] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if (self.bike_id is None) == (self.bike_freetext is None):
            raise ValueError(
                "set exactly one of bike_id (catalog) or bike_freetext (other/unknown)"
            )
        row_ids = [row.row_id for row in self.rows]
        if len(row_ids) != len(set(row_ids)):
            raise ValueError("row_id values must be unique")
        unknown = set(self.answers) - set(row_ids)
        if unknown:
            raise ValueError(f"answers refer to rows that don't exist: {sorted(unknown)}")
        return self


# --- Triage (what the agent produces, per row) ----------------------------------------------


class RowAssessment(Strict):
    """The assessment of one complaint row from the intake form."""

    row_id: str = Field(description="The row_id of the complaint row this assessment is for.")
    severity: Severity = Field(
        description=(
            "safety_critical: unsafe to ride until fixed (braking, steering, fork, frame, or "
            "wheel retention at risk); the customer must be told not to ride it. "
            "needs_service: needs shop work (service labor or parts), but not an immediate "
            "safety risk. "
            "needs_adjustment: works, but a quick adjustment or settings change fixes it "
            "(indexing, brake rub, suspension setup); no parts. "
            "cosmetic: a real, visible issue that doesn't affect function or safety. Damage "
            "that could hide structural damage (e.g. a carbon frame or fork after a crash) is "
            "never cosmetic; treat it as safety_critical until inspected. "
            "no_action_needed: working as intended; explain to the customer why it's normal."
        )
    )
    likely_causes: list[str] = Field(
        min_length=1,
        max_length=5,
        description="Most likely causes, most likely first. Short phrases.",
    )
    agrees_with_suspected_area: bool = Field(
        description="Whether the evidence supports the suspected area the staff member picked."
    )
    disagreement_reason: str | None = Field(
        default=None,
        description=(
            "Required when agrees_with_suspected_area is false, otherwise null: a short, polite "
            "reason the evidence points elsewhere."
        ),
    )
    question_for_customer: str | None = Field(
        default=None,
        description=(
            "One question for the staff member to ask the customer, only if the answer would "
            "change the assessment. Otherwise null."
        ),
    )
    suggested_labor: list[LaborCode] = Field(
        default_factory=list,
        description="Labor codes from the shop's service menu. Never invent codes.",
    )
    suggested_part_categories: list[PartCategory] = Field(
        default_factory=list,
        description="Part categories likely needed. Empty when adjustment or labor alone fixes it.",
    )
    citations: list[str] = Field(
        default_factory=list,
        description="IDs of the knowledge chunks that support this assessment.",
    )

    @model_validator(mode="after")
    def _reason_matches_agreement(self) -> Self:
        if self.agrees_with_suspected_area and self.disagreement_reason is not None:
            raise ValueError("disagreement_reason must be null when agreeing")
        if not self.agrees_with_suspected_area and not self.disagreement_reason:
            raise ValueError("disagreement_reason is required when disagreeing")
        return self


class TriageResult(Strict):
    assessments: list[RowAssessment] = Field(min_length=1)

    @computed_field
    @property
    def overall_severity(self) -> Severity:
        return max_severity(a.severity for a in self.assessments)

    @computed_field
    @property
    def escalated(self) -> bool:
        return self.overall_severity is Severity.SAFETY_CRITICAL


# --- Compatibility (deterministic engine output) --------------------------------------------


class CompatStatus(StrEnum):
    COMPATIBLE = "compatible"
    INCOMPATIBLE = "incompatible"
    # No rule or data covers the case. Never shown to a customer as a fit: a draft may only
    # carry it flagged "unverified, mechanic to confirm".
    UNKNOWN = "unknown"


class WheelPosition(StrEnum):
    FRONT = "front"
    REAR = "rear"


class CompatResult(Strict):
    part_id: Slug
    status: CompatStatus
    reasons: list[str] = Field(min_length=1)
    requires_adapter: str | None = None
    # Set for parts checked per wheel (tires, tubes, rotors); a mullet differs front and rear.
    position: WheelPosition | None = None

    @model_validator(mode="after")
    def _adapter_only_if_compatible(self) -> Self:
        if self.requires_adapter and self.status is not CompatStatus.COMPATIBLE:
            raise ValueError("only a compatible part can require an adapter")
        return self


# --- Work order draft: the LLM picks lines, code supplies prices and does the math ------------


class LaborLine(Strict):
    code: LaborCode
    qty: int = Field(ge=1, le=10)
    unit_price_cents: int = Field(ge=0, description="From the labor menu, never from the LLM.")

    @computed_field
    @property
    def line_total_cents(self) -> int:
        return self.qty * self.unit_price_cents


class PartLine(Strict):
    part_id: Slug
    qty: int = Field(ge=1, le=10)
    unit_price_cents: int = Field(ge=0, description="From the parts catalog, never from the LLM.")
    position: WheelPosition | None = None
    # A fit the engine couldn't confirm, and why; the reviewing mechanic must check it.
    unverified: bool = False
    unverified_reason: str | None = None

    @model_validator(mode="after")
    def _reason_iff_unverified(self) -> Self:
        if self.unverified != (self.unverified_reason is not None):
            raise ValueError("unverified parts need an unverified_reason, and only they have one")
        return self

    @computed_field
    @property
    def line_total_cents(self) -> int:
        return self.qty * self.unit_price_cents


class WorkOrderStatus(StrEnum):
    DRAFT = "draft"
    AWAITING_REVIEW = "awaiting_review"  # where every agent draft lands
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"


class WorkOrderDraft(Strict):
    bike_id: Slug | None = None
    bike_freetext: ShortText | None = None
    severity: Severity
    labor_lines: list[LaborLine] = Field(default_factory=list)
    part_lines: list[PartLine] = Field(default_factory=list)
    customer_explanation: LongText
    mechanic_notes: LongText | None = None
    citations: list[str] = Field(default_factory=list)

    @computed_field
    @property
    def estimate_total_cents(self) -> int:
        lines = [*self.labor_lines, *self.part_lines]
        return sum(line.line_total_cents for line in lines)
