"""Guardrails applied at the boundary, before the graph starts.

LangSmith records the graph's input, so redaction inside the graph would be too late: the raw
intake would already be in the trace. Callers (the CLI, later the API) run apply_guardrails
first and pass only the redacted intake in.
"""

from __future__ import annotations

from collections import Counter

from pydantic import BaseModel

from counterwrench.guardrails.injection import flag
from counterwrench.guardrails.pii import redact
from counterwrench.models import IntakeForm


class GuardrailFlag(BaseModel):
    field: str  # e.g. "rows.r1.note", "general_notes"
    kind: str  # instruction_override | role_tag | approval_pressure | out_of_scope


class GuardrailResult(BaseModel):
    intake: IntakeForm  # redacted
    pii_counts: dict[str, int]  # by type; never the values
    flags: list[GuardrailFlag]

    def mechanic_note(self) -> str | None:
        """What the reviewing mechanic should know, added to the draft by code."""
        if not self.flags:
            return None
        found = "; ".join(f"{f.kind} in {f.field}" for f in self.flags)
        return (
            f"Guardrail: this intake contained instruction-like or off-topic text ({found}). "
            "It was treated as customer input, not instructions; check the draft with that in mind."
        )


def apply_guardrails(intake: IntakeForm) -> GuardrailResult:
    counts: Counter = Counter()
    flags: list[GuardrailFlag] = []

    def guard(field: str, text: str | None) -> str | None:
        if text is None:
            return None
        flags.extend(GuardrailFlag(field=field, kind=kind) for kind in flag(text))
        redacted, found = redact(text)
        counts.update(found)
        return redacted

    rows = [
        row.model_copy(update={"note": guard(f"rows.{row.row_id}.note", row.note)})
        for row in intake.rows
    ]
    answers = {
        row_id: guard(f"answers.{row_id}", answer) for row_id, answer in intake.answers.items()
    }
    redacted = intake.model_copy(
        update={
            "rows": rows,
            "answers": answers,
            "general_notes": guard("general_notes", intake.general_notes),
            "bike_freetext": guard("bike_freetext", intake.bike_freetext),
        }
    )
    return GuardrailResult(
        intake=IntakeForm.model_validate(redacted.model_dump()),
        pii_counts=dict(counts),
        flags=flags,
    )
