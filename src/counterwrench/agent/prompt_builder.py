"""Turn an IntakeForm into the text the agent reads, deterministically.

Picklist values are trusted (they come from our taxonomy). Free text (notes, staff answers,
general notes, free-text bike descriptions) is customer/staff input: it's wrapped in tags marked
untrusted="true", and its angle brackets are escaped, so a note can never close a tag early and
pass itself off as instructions. The system prompt tells the model that text inside untrusted
tags is data, never instructions.
"""

from __future__ import annotations

from counterwrench.catalog import BikeSpec
from counterwrench.models import ComplaintRow, IntakeForm
from counterwrench.rag.chunks import bike_chunks
from counterwrench.taxonomy import SuspectedArea


def escape(text: str) -> str:
    """Neutralize markup in free text so it can't break out of its tag."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def label(value: str) -> str:
    """'poor_shifting' -> 'Poor shifting'."""
    return value.replace("_", " ").capitalize()


def _untrusted(tag: str, text: str) -> str:
    return f'<{tag} untrusted="true">{escape(text)}</{tag}>'


def bike_name(bike: BikeSpec) -> str:
    return f"{bike.year} {bike.make} {bike.model}"


def _bike_block(intake: IntakeForm, bike: BikeSpec | None) -> str:
    if bike is not None:
        specs = bike_chunks([bike])[0].content
        return f'<bike source="catalog" id="{bike.id}">\n{specs}\n</bike>'
    if intake.bike_id:
        return (
            f'<bike source="catalog" id="{escape(intake.bike_id)}">\n'
            "This bike id is not in the catalog. Treat the bike as unknown: no parts can be "
            "checked.\n</bike>"
        )
    return (
        '<bike source="customer">\n'
        + _untrusted("description", intake.bike_freetext or "")
        + "\nNot in the catalog: no parts can be checked for compatibility.\n</bike>"
    )


def _row_block(row: ComplaintRow, answer: str | None) -> str:
    lines = [
        f'<row id="{row.row_id}">',
        f"  complaint: {label(row.complaint)}",
        f"  staff suspected area: {label(row.suspected_area)}",
    ]
    if row.note:
        lines.append("  " + _untrusted("customer_note", row.note))
    if answer:
        lines.append("  " + _untrusted("staff_answer", answer))
    lines.append("</row>")
    return "\n".join(lines)


def build_intake_message(intake: IntakeForm, bike: BikeSpec | None) -> str:
    """The intake as the agent sees it. `bike` is the resolved catalog bike, if any."""
    parts = ["<intake>", _bike_block(intake, bike)]
    parts += [_row_block(row, intake.answers.get(row.row_id)) for row in intake.rows]
    if intake.general_notes:
        parts.append(_untrusted("general_notes", intake.general_notes))
    parts.append("</intake>")
    return "\n".join(parts)


def retrieval_query(row: ComplaintRow, bike: BikeSpec | None, answer: str | None = None) -> str:
    """Search query for one row: bike name, complaint, suspected area AND the free text.
    Picklist-only queries miss the cases that matter most: a "squeak" whose note says
    "metal on metal grinding" must reach the grinding (safety) section."""
    parts = []
    if bike is not None:
        parts.append(bike_name(bike))
    parts.append(label(row.complaint))
    if row.suspected_area != SuspectedArea.UNSURE:
        parts.append(label(row.suspected_area))
    if row.note:
        parts.append(row.note)
    if answer:
        parts.append(answer)
    return ". ".join(parts)
