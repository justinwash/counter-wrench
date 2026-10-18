"""Consistency checks on the real catalog (data/seed). These fail when the data drifts, e.g. a
caliper renamed in bikes.yaml without updating its pad rule, before a customer ever sees it."""

import pytest

from counterwrench.catalog import BikeSpec
from counterwrench.compat.engine import Rules, check_all_positions
from counterwrench.db.seed import load_seed
from counterwrench.models import BrakeType, CompatStatus, PartCategory

DATA = load_seed()
BIKES = [BikeSpec.model_validate(b.model_dump(exclude={"source"})) for b in DATA.bikes]
RULES = Rules(DATA.compat_rules)


def rules_of(rule_type: str):
    return [r for r in DATA.compat_rules if r.rule_type == rule_type]


def test_every_caliper_has_a_pad_rule():
    calipers = {b.brake_caliper for b in BIKES}
    assert calipers <= {r.bike_value for r in rules_of("caliper_pad")}


def test_every_pad_rule_points_at_a_real_pad_shape():
    shapes = {p.specs.pad_shape for p in DATA.parts if p.category == "brake_pads"}
    assert {r.part_value for r in rules_of("caliper_pad")} <= shapes


def test_every_pad_rule_points_at_a_real_caliper():
    # A rule for a caliper no bike has is usually a leftover from a rename.
    assert {r.bike_value for r in rules_of("caliper_pad")} <= {b.brake_caliper for b in BIKES}


def test_every_bike_freehub_has_rules():
    assert {b.freehub for b in BIKES} <= {r.bike_value for r in rules_of("freehub_cassette")}


# Categories every bike should have at least one usable part in (rotors only for disc brakes).
CATEGORIES = [
    PartCategory.CASSETTE,
    PartCategory.CHAIN,
    PartCategory.REAR_DERAILLEUR,
    PartCategory.BRAKE_PADS,
    PartCategory.BOTTOM_BRACKET,
    PartCategory.TIRE,
    PartCategory.ROTOR,
]


@pytest.mark.parametrize("bike", BIKES, ids=lambda b: b.id)
@pytest.mark.parametrize("category", CATEGORIES, ids=str)
def test_every_bike_has_a_part_that_fits(bike, category):
    if category is PartCategory.ROTOR and bike.brake_type is BrakeType.RIM:
        pytest.skip("rim brakes")
    results = [
        r for p in DATA.parts if p.category == category for r in check_all_positions(bike, p, RULES)
    ]
    positions = {r.position for r in results}
    for position in positions:
        usable = [
            r
            for r in results
            if r.position == position and r.status is not CompatStatus.INCOMPATIBLE
        ]
        assert usable, f"no {category} fits {bike.id} ({position or 'bike'})"
