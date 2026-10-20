"""Pure compatibility checks: no database, no LLM, fully deterministic.

Every check produces findings (a status and a human-readable reason); they combine as:
any `incompatible` -> incompatible; else any `unknown` -> unknown; else compatible.
Missing data is `unknown`, never a guess. Upgrade paths must be explicit in the data
(a rule with an adapter); anything that would be solely the mechanic's call is
`incompatible` (e.g. a rotor size different from stock).

Rule tables list what fits. For a bike value that has rules (a known caliper or freehub), a
part value with no rule is incompatible; a bike value with no rules at all is unknown.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from counterwrench.catalog import BikeSpec, CompatRule, WheelSize
from counterwrench.models import BrakeType, CompatResult, CompatStatus, PartCategory, WheelPosition

COMPATIBLE, INCOMPATIBLE, UNKNOWN = (
    CompatStatus.COMPATIBLE,
    CompatStatus.INCOMPATIBLE,
    CompatStatus.UNKNOWN,
)

# Parts checked separately for each wheel.
PER_WHEEL = {PartCategory.TIRE, PartCategory.TUBE, PartCategory.ROTOR}


@dataclass(frozen=True)
class Finding:
    status: CompatStatus
    reason: str
    adapter: str | None = None


class Rules:
    """compat_rules indexed for lookup."""

    def __init__(self, rules: Iterable[CompatRule]):
        self._exact: dict[tuple[str, str, str], CompatRule] = {}
        self._known_bike_values: set[tuple[str, str]] = set()
        for rule in rules:
            self._exact[(rule.rule_type, rule.bike_value, rule.part_value)] = rule
            self._known_bike_values.add((rule.rule_type, rule.bike_value))

    def find(self, rule_type: str, bike_value: str, part_value: str, *, what: str) -> Finding:
        rule = self._exact.get((rule_type, bike_value, part_value))
        if rule is None and (rule_type, bike_value) not in self._known_bike_values:
            return Finding(UNKNOWN, f"No {what} rule covers {bike_value}; a mechanic must confirm.")
        if rule is None or not rule.compatible:
            note = f" {rule.note}" if rule and rule.note else ""
            return Finding(INCOMPATIBLE, f"{part_value} doesn't fit {bike_value} ({what}).{note}")
        note = f" {rule.note}" if rule.note else ""
        return Finding(COMPATIBLE, f"{part_value} fits {bike_value} ({what}).{note}", rule.adapter)


def check(
    bike: BikeSpec,
    part,
    rules: Rules,
    position: WheelPosition | None = None,
    tire_width_mm: int | None = None,
) -> CompatResult:
    """Check one part against one bike. Per-wheel parts (tires, tubes, rotors) need a position;
    tubes also need the installed tire width, or the result is unknown."""
    category = PartCategory(part.category)
    if (category in PER_WHEEL) != (position is not None):
        raise ValueError(
            f"{category} parts {'need' if category in PER_WHEEL else 'take no'} position"
        )
    findings = _CHECKS[category](bike, part.specs, rules, position, tire_width_mm)
    return _combine(part.id, findings, position)


def check_all_positions(
    bike: BikeSpec, part, rules: Rules, tire_width_mm: int | None = None
) -> list[CompatResult]:
    """One result for most parts; one per wheel for tires, tubes and rotors."""
    if PartCategory(part.category) in PER_WHEEL:
        return [check(bike, part, rules, p, tire_width_mm) for p in WheelPosition]
    return [check(bike, part, rules)]


def _combine(part_id: str, findings: list[Finding], position) -> CompatResult:
    for status in (INCOMPATIBLE, UNKNOWN, COMPATIBLE):
        if any(f.status is status for f in findings):
            break
    # Lead with the findings that decided the outcome.
    ordered = sorted(findings, key=lambda f: f.status is not status)
    adapters = [f.adapter for f in findings if f.adapter]
    return CompatResult(
        part_id=part_id,
        status=status,
        reasons=[f.reason for f in ordered],
        requires_adapter="; ".join(adapters) if adapters and status is COMPATIBLE else None,
        position=position,
    )


def _speeds(bike: BikeSpec, speeds: int, what: str) -> Finding:
    if speeds == bike.drivetrain_speeds:
        return Finding(COMPATIBLE, f"{speeds}-speed {what} matches the {speeds}-speed drivetrain.")
    return Finding(
        INCOMPATIBLE, f"{speeds}-speed {what} on a {bike.drivetrain_speeds}-speed drivetrain."
    )


def _wheel(bike: BikeSpec, position: WheelPosition) -> WheelSize:
    return WheelSize(
        bike.front_wheel_bsd_mm if position is WheelPosition.FRONT else bike.rear_wheel_bsd_mm
    )


def _wheel_size(bike: BikeSpec, bsd: int, position: WheelPosition) -> Finding:
    wheel, part_size = _wheel(bike, position), WheelSize(bsd)
    if part_size == wheel:
        return Finding(COMPATIBLE, f"Fits the {position} wheel, {wheel.label}.")
    return Finding(
        INCOMPATIBLE, f"Made for {part_size.label}; the {position} wheel is {wheel.label}."
    )


# --- Per-category checks ---------------------------------------------------------------------


def _shift_family(
    bike: BikeSpec, part_family: str, rules: Rules, rule_type: str, what: str
) -> Finding:
    """Strict: same family, or an explicit cross-family rule. Anything else is incompatible,
    since mixing shifting systems is a mechanic's call, not a parts-counter answer."""
    if part_family == bike.shift_family:
        return Finding(COMPATIBLE, f"Same shift family ({bike.shift_family}).")
    cross = rules.find(rule_type, bike.shift_family, part_family, what="shift family")
    if cross.status is COMPATIBLE:
        return cross
    return Finding(
        INCOMPATIBLE,
        f"{part_family} {what} doesn't match the bike's {bike.shift_family} shifting.",
    )


def _cassette(bike, specs, rules, position, tire_width_mm) -> list[Finding]:
    return [
        rules.find("freehub_cassette", bike.freehub, specs.freehub, what="freehub"),
        _speeds(bike, specs.speeds, "cassette"),
        # Cog spacing and range belong to the shifting system, not just the freehub.
        _shift_family(bike, specs.shift_family, rules, "shift_family_cassette", "cassette"),
    ]


def _chain(bike, specs, rules, position, tire_width_mm) -> list[Finding]:
    findings = [_speeds(bike, specs.speeds, "chain")]
    required = bike.required_chain_type
    if required and specs.chain_type != required:
        findings.append(Finding(INCOMPATIBLE, f"This drivetrain requires a {required} chain."))
    elif required:
        findings.append(Finding(COMPATIBLE, f"{required} chain, as this drivetrain requires."))
    return findings


def _rear_derailleur(bike, specs, rules, position, tire_width_mm) -> list[Finding]:
    findings = [
        _speeds(bike, specs.speeds, "derailleur"),
        # Cable pull (or electronic protocol) must match the shifters.
        _shift_family(bike, specs.shift_family, rules, "shift_family", "derailleur"),
    ]
    if specs.mount == "udh_direct" and not bike.udh:
        findings.append(
            Finding(INCOMPATIBLE, "Direct-mount (T-Type) derailleur needs a UDH frame.")
        )
    return findings


def _brake_pads(bike, specs, rules, position, tire_width_mm) -> list[Finding]:
    if not bike.brake_caliper:
        return [Finding(UNKNOWN, "The bike's brake caliper isn't recorded.")]
    return [rules.find("caliper_pad", bike.brake_caliper, specs.pad_shape, what="caliper/pad")]


def _rotor(bike, specs, rules, position, tire_width_mm) -> list[Finding]:
    if bike.brake_type is BrakeType.RIM:
        return [Finding(INCOMPATIBLE, "Rim brakes: this bike has no rotors.")]
    findings = []
    if specs.mount == bike.rotor_mount:
        findings.append(Finding(COMPATIBLE, f"{specs.mount} mount matches."))
    else:
        findings.append(Finding(INCOMPATIBLE, f"{specs.mount} rotor on a {bike.rotor_mount} hub."))
    stock = bike.front_rotor_mm if position is WheelPosition.FRONT else bike.rear_rotor_mm
    if specs.size_mm == stock:
        findings.append(Finding(COMPATIBLE, f"{stock} mm matches the stock {position} rotor."))
    else:
        findings.append(
            Finding(
                INCOMPATIBLE,
                f"{specs.size_mm} mm rotor; the stock {position} rotor is {stock} mm. A size "
                "change needs a different caliper adapter and is an upgrade, not a replacement.",
            )
        )
    return findings


def _bottom_bracket(bike, specs, rules, position, tire_width_mm) -> list[Finding]:
    findings = []
    if specs.bb_standard == bike.bb_standard:
        findings.append(Finding(COMPATIBLE, f"Fits the {bike.bb_standard} shell."))
    else:
        findings.append(
            Finding(INCOMPATIBLE, f"{specs.bb_standard} BB; the frame is {bike.bb_standard}.")
        )
    if specs.spindle == bike.crank_spindle:
        findings.append(Finding(COMPATIBLE, f"Fits the {bike.crank_spindle} crank spindle."))
    else:
        findings.append(
            Finding(
                INCOMPATIBLE,
                f"Made for a {specs.spindle} spindle; the crank is {bike.crank_spindle}.",
            )
        )
    return findings


def _tire(bike, specs, rules, position, tire_width_mm) -> list[Finding]:
    findings = [_wheel_size(bike, specs.wheel_bsd_mm, position)]
    if bike.max_tire_mm is None:
        findings.append(Finding(UNKNOWN, "The frame's max tire width isn't recorded."))
    elif specs.width_mm <= bike.max_tire_mm:
        findings.append(
            Finding(COMPATIBLE, f"{specs.width_mm} mm is within the {bike.max_tire_mm} mm max.")
        )
    else:
        findings.append(
            Finding(
                INCOMPATIBLE, f"{specs.width_mm} mm is wider than the {bike.max_tire_mm} mm max."
            )
        )
    return findings


def _tube(bike, specs, rules, position, tire_width_mm) -> list[Finding]:
    if specs.generic:
        return [Finding(UNKNOWN, "Generic tube: the mechanic sizes it to the installed tire.")]
    findings = [_wheel_size(bike, specs.wheel_bsd_mm, position)]
    if tire_width_mm is None:
        findings.append(Finding(UNKNOWN, "Need the installed tire width to size the tube."))
    elif specs.min_width_mm <= tire_width_mm <= specs.max_width_mm:
        findings.append(Finding(COMPATIBLE, f"Covers a {tire_width_mm} mm tire."))
    else:
        findings.append(
            Finding(
                INCOMPATIBLE,
                f"Sized {specs.min_width_mm}-{specs.max_width_mm} mm; "
                f"the tire is {tire_width_mm} mm.",
            )
        )
    return findings


_CHECKS = {
    PartCategory.CASSETTE: _cassette,
    PartCategory.CHAIN: _chain,
    PartCategory.REAR_DERAILLEUR: _rear_derailleur,
    PartCategory.BRAKE_PADS: _brake_pads,
    PartCategory.ROTOR: _rotor,
    PartCategory.BOTTOM_BRACKET: _bottom_bracket,
    PartCategory.TIRE: _tire,
    PartCategory.TUBE: _tube,
}
