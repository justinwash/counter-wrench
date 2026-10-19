"""Build every retrieval chunk: knowledge-base sections, plus chunks generated from the labor
menu and bike catalog (never hand-written, so they can't drift from the data)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from counterwrench.catalog import BikeSpec, LaborItem, WheelSize
from counterwrench.rag.docs import Doc


@dataclass(frozen=True)
class Chunk:
    id: str
    source: str  # doc | labor | bike
    doc_type: str
    title: str
    heading: str
    content: str
    bike_ids: tuple[str, ...] = field(default_factory=tuple)
    complaints: tuple[str, ...] = field(default_factory=tuple)

    @property
    def text(self) -> str:
        """What gets embedded: title and heading first, so a chunk makes sense on its own."""
        return f"{self.title} - {self.heading}\n\n{self.content}"

    @property
    def content_hash(self) -> str:
        parts = [self.text, ",".join(self.bike_ids), ",".join(self.complaints), self.doc_type]
        return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


def doc_chunks(docs: list[Doc]) -> list[Chunk]:
    return [
        Chunk(
            id=f"{doc.doc_id}#{section.anchor}",
            source="doc",
            doc_type=doc.meta.doc_type.value,
            title=doc.meta.title,
            heading=section.heading,
            content=section.body,
            bike_ids=tuple(doc.meta.bike_ids),
            complaints=tuple(c.value for c in doc.meta.complaints),
        )
        for doc in docs
        for section in doc.sections
    ]


def labor_chunks(items: list[LaborItem]) -> list[Chunk]:
    return [
        Chunk(
            id=f"labor#{item.code}",
            source="labor",
            doc_type="labor_menu",
            title="Service menu",
            heading=f"{item.code}: {item.name}",
            content=(
                f"{item.code} ({item.name}) costs ${item.price_cents / 100:.2f} flat rate and "
                f"takes about {item.est_minutes} minutes. {item.description} "
                f"Category: {item.category}."
            ),
        )
        for item in items
    ]


def _yes(value: bool) -> str:
    return "yes" if value else "no"


def bike_chunks(bikes: list[BikeSpec]) -> list[Chunk]:
    chunks = []
    for bike in bikes:
        name = f"{bike.year} {bike.make} {bike.model}"
        if bike.brake_type == "rim":
            brakes = f"Brakes: rim ({bike.brake_caliper}), no rotors."
        else:
            brakes = (
                f"Brakes: {bike.brake_type.replace('_', ' ')} ({bike.brake_caliper}); "
                f"{bike.rotor_mount} rotors, {bike.front_rotor_mm} mm front, "
                f"{bike.rear_rotor_mm} mm rear."
            )
        lines = [
            f"{name}, {bike.category} bike.",
            f"Wheels: front {WheelSize(bike.front_wheel_bsd_mm).label}, "
            f"rear {WheelSize(bike.rear_wheel_bsd_mm).label}.",
            "Max tire width: "
            + (f"{bike.max_tire_mm} mm." if bike.max_tire_mm else "not on file."),
            f"Drivetrain: {bike.drivetrain_speeds}-speed, shift family {bike.shift_family}, "
            f"{bike.freehub} freehub, {bike.rear_axle} rear axle.",
            f"Bottom bracket: {bike.bb_standard} shell, {bike.crank_spindle} crank spindle.",
            brakes,
            f"UDH frame: {_yes(bike.udh)}. Dropper post: {_yes(bike.dropper_post)}.",
        ]
        if bike.required_chain_type:
            lines.append(f"Requires a {bike.required_chain_type} chain.")
        chunks.append(
            Chunk(
                id=f"bike#{bike.id}",
                source="bike",
                doc_type="bike_spec",
                title="Bike spec sheet",
                heading=name,
                content="\n".join(lines),
                bike_ids=(bike.id,),
            )
        )
    return chunks
