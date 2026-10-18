"""Complaint taxonomy: the single source of truth for the intake picklists.

Drives the `ComplaintRow` enums, the API schema (and so the UI's TypeScript types), and the
`complaint_taxonomy` table, which is seeded from `pairs()`. The map lists the areas counter
staff may pick for each complaint: the plausible ones, not just the likely ones, since the
agent can disagree with whatever staff pick.
"""

from __future__ import annotations

from enum import StrEnum


class Complaint(StrEnum):
    SQUEAK = "squeak"
    CREAK = "creak"
    CLICK = "click"
    POOR_SHIFTING = "poor_shifting"
    SKIPPING = "skipping"
    CHAIN_DROP = "chain_drop"
    BRAKE_RUB = "brake_rub"
    BRAKE_NOISE = "brake_noise"
    SOFT_BRAKE_LEVER = "soft_brake_lever"
    WEAK_BRAKING = "weak_braking"
    WOBBLE = "wobble"
    FLAT_TIRE = "flat_tire"
    SLOW_LEAK = "slow_leak"
    SUSPENSION_PACKING_UP = "suspension_packing_up"
    SUSPENSION_BOUNCING = "suspension_bouncing"
    SUSPENSION_BOTTOMING = "suspension_bottoming"
    SUSPENSION_HARSH = "suspension_harsh"
    SUSPENSION_STICKY = "suspension_sticky"
    SUSPENSION_LEAKING = "suspension_leaking"
    SUSPENSION_KNOCK = "suspension_knock"
    DROPPER_ISSUE = "dropper_issue"
    OTHER = "other"


class SuspectedArea(StrEnum):
    # Drivetrain
    CHAIN = "chain"
    CASSETTE = "cassette"
    FREEHUB = "freehub"
    CHAINRINGS = "chainrings"
    CRANKSET = "crankset"
    BOTTOM_BRACKET = "bottom_bracket"
    PEDALS = "pedals"
    CLEATS = "cleats"
    REAR_DERAILLEUR = "rear_derailleur"
    FRONT_DERAILLEUR = "front_derailleur"
    DERAILLEUR_HANGER = "derailleur_hanger"
    SHIFTER = "shifter"
    CABLES_HOUSING = "cables_housing"
    # Brakes
    BRAKE_PADS = "brake_pads"
    ROTOR = "rotor"
    CALIPER = "caliper"
    BRAKE_LEVER = "brake_lever"
    BRAKE_HYDRAULICS = "brake_hydraulics"
    # Wheels and tires (`rim` is also the braking surface on rim-brake bikes)
    WHEEL_TRUE = "wheel_true"
    HUB = "hub"
    SPOKES = "spokes"
    RIM = "rim"
    AXLE = "axle"
    TIRE = "tire"
    TUBE = "tube"
    RIM_TAPE = "rim_tape"
    TUBELESS_SETUP = "tubeless_setup"
    VALVE = "valve"
    # Frame, cockpit, contact points
    FRAME = "frame"
    FRAME_PIVOTS = "frame_pivots"
    HEADSET = "headset"
    HANDLEBAR_STEM = "handlebar_stem"
    SEATPOST = "seatpost"
    SADDLE = "saddle"
    DROPPER_POST = "dropper_post"
    # Suspension (`suspension_setup` = pressure, sag, rebound, compression: an adjustment)
    FORK = "fork"
    REAR_SHOCK = "rear_shock"
    SUSPENSION_SETUP = "suspension_setup"
    UNSURE = "unsure"


A = SuspectedArea
_SUSPENSION = frozenset({A.SUSPENSION_SETUP, A.FORK, A.REAR_SHOCK})

# `unsure` is always allowed and `other` allows every area; neither is listed here.
_ALLOWED: dict[Complaint, frozenset[SuspectedArea]] = {
    Complaint.SQUEAK: frozenset(
        {A.CHAIN, A.PEDALS, A.CLEATS, A.SADDLE, A.SEATPOST, A.FRAME_PIVOTS}
    ),
    # `frame` on purpose: a cracked frame often shows up first as a creak.
    Complaint.CREAK: frozenset(
        {
            A.BOTTOM_BRACKET,
            A.CRANKSET,
            A.PEDALS,
            A.CLEATS,
            A.SEATPOST,
            A.SADDLE,
            A.HEADSET,
            A.HANDLEBAR_STEM,
            A.AXLE,
            A.FRAME_PIVOTS,
            A.FRAME,
        }
    ),  # fmt: skip
    Complaint.CLICK: frozenset(
        {A.PEDALS, A.CLEATS, A.CRANKSET, A.CHAINRINGS, A.SPOKES, A.AXLE, A.REAR_DERAILLEUR}
    ),
    Complaint.POOR_SHIFTING: frozenset(
        {
            A.SHIFTER,
            A.CABLES_HOUSING,
            A.REAR_DERAILLEUR,
            A.FRONT_DERAILLEUR,
            A.DERAILLEUR_HANGER,
            A.CHAIN,
            A.CASSETTE,
        }
    ),  # fmt: skip
    Complaint.SKIPPING: frozenset(
        {
            A.CHAIN,
            A.CASSETTE,
            A.CHAINRINGS,
            A.FREEHUB,
            A.REAR_DERAILLEUR,
            A.DERAILLEUR_HANGER,
            A.CABLES_HOUSING,
        }
    ),  # fmt: skip
    Complaint.CHAIN_DROP: frozenset({A.FRONT_DERAILLEUR, A.CHAINRINGS, A.CHAIN, A.REAR_DERAILLEUR}),
    Complaint.BRAKE_RUB: frozenset({A.ROTOR, A.CALIPER, A.BRAKE_PADS, A.WHEEL_TRUE, A.AXLE, A.RIM}),
    Complaint.BRAKE_NOISE: frozenset({A.BRAKE_PADS, A.ROTOR, A.CALIPER, A.RIM}),
    Complaint.SOFT_BRAKE_LEVER: frozenset(
        {A.BRAKE_HYDRAULICS, A.BRAKE_PADS, A.CABLES_HOUSING, A.BRAKE_LEVER}
    ),
    Complaint.WEAK_BRAKING: frozenset(
        {A.BRAKE_PADS, A.ROTOR, A.RIM, A.BRAKE_HYDRAULICS, A.CABLES_HOUSING, A.CALIPER}
    ),
    Complaint.WOBBLE: frozenset({A.WHEEL_TRUE, A.HUB, A.TIRE, A.AXLE, A.HEADSET, A.FORK, A.FRAME}),
    Complaint.FLAT_TIRE: frozenset({A.TUBE, A.TIRE, A.RIM_TAPE, A.TUBELESS_SETUP, A.VALVE}),
    Complaint.SLOW_LEAK: frozenset({A.TUBELESS_SETUP, A.VALVE, A.RIM_TAPE, A.TIRE}),
    Complaint.SUSPENSION_PACKING_UP: _SUSPENSION,
    Complaint.SUSPENSION_BOUNCING: _SUSPENSION,
    Complaint.SUSPENSION_BOTTOMING: _SUSPENSION,
    Complaint.SUSPENSION_HARSH: _SUSPENSION,
    Complaint.SUSPENSION_STICKY: _SUSPENSION,
    Complaint.SUSPENSION_LEAKING: frozenset({A.FORK, A.REAR_SHOCK}),
    # `headset` on purpose: a loose headset feels just like a fork knock.
    Complaint.SUSPENSION_KNOCK: frozenset({A.FORK, A.REAR_SHOCK, A.FRAME_PIVOTS, A.HEADSET}),
    Complaint.DROPPER_ISSUE: frozenset({A.DROPPER_POST, A.CABLES_HOUSING}),
}


def allowed_areas(complaint: Complaint) -> frozenset[SuspectedArea]:
    if complaint is Complaint.OTHER:
        return frozenset(SuspectedArea)
    return _ALLOWED[complaint] | {SuspectedArea.UNSURE}


def is_allowed(complaint: Complaint, area: SuspectedArea) -> bool:
    return area in allowed_areas(complaint)


def pairs() -> list[tuple[str, str]]:
    """Every allowed (complaint, area) pair, sorted: the rows for `complaint_taxonomy`."""
    return sorted((c.value, a.value) for c in Complaint for a in allowed_areas(c))
