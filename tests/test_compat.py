import pytest

from counterwrench.catalog import BikeSpec, CompatRule
from counterwrench.compat.engine import PER_WHEEL, Rules, check, check_all_positions
from counterwrench.db.seed import load_seed
from counterwrench.models import CompatStatus, PartCategory, WheelPosition

OK, NO, UNKNOWN = CompatStatus.COMPATIBLE, CompatStatus.INCOMPATIBLE, CompatStatus.UNKNOWN
FRONT, REAR = WheelPosition.FRONT, WheelPosition.REAR

DATA = load_seed()
BIKES = {b.id: BikeSpec.model_validate(b.model_dump(exclude={"source"})) for b in DATA.bikes}
PARTS = {p.id: p for p in DATA.parts}
RULES = Rules(DATA.compat_rules)

HIGHTOWER = "santa-cruz-hightower-r-carbon-c-2024"
SUPERCALIBER = "trek-supercaliber-sl-9-7-gx-axs-gen-2-2025"
SLASH = "trek-slash-9-8-xt-gen-6-2024"
CHECKPOINT = "trek-checkpoint-alr-5-gen-3-2026"
CAAD10 = "cannondale-caad10-5-105-2014"
FUEL_2023 = "trek-fuel-ex-8-gen-6-2023"
FUEL_2012 = "trek-fuel-ex-8-2012"
MARLIN_2025 = "trek-marlin-7-gen-3-2025"
EMONDA = "trek-emonda-sl-6-2023"
TOPSTONE = "cannondale-topstone-2-2023"


def status(bike_id, part_id, position=None, tire_width_mm=None):
    return check(BIKES[bike_id], PARTS[part_id], RULES, position, tire_width_mm).status


# --- Named real-catalog cases ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("bike", "part", "position", "expected"),
    [
        # Cassettes: freehub decides, then speeds.
        (HIGHTOWER, "shimano-cs-m7100-10-51", None, NO),  # HG freehub, Micro Spline cassette
        (HIGHTOWER, "sram-pg-1230-11-50", None, OK),
        (FUEL_2023, "shimano-cs-m7100-10-51", None, OK),
        (FUEL_2023, "sram-pg-1230-11-50", None, NO),  # Micro Spline freehub, HG cassette
        (SUPERCALIBER, "sram-xs-1275-10-52", None, OK),  # XD
        (FUEL_2012, "shimano-cs-m8000-11-46", None, NO),  # 11-speed on a 10-speed drivetrain
        (FUEL_2012, "shimano-cs-m4100-11-46", None, OK),
        # Cassettes also match the shifting system: right freehub and speeds isn't enough.
        (HIGHTOWER, "shimano-cs-r7101-11-34", None, NO),  # road cassette on SRAM Eagle MTB
        (HIGHTOWER, "sram-pg-1231-11-44", None, NO),  # XPLR gravel cassette on Eagle MTB
        (CHECKPOINT, "sram-pg-1231-11-44", None, OK),
        (EMONDA, "shimano-cs-r7101-11-34", None, OK),  # Di2 uses the mechanical cassette (rule)
        (TOPSTONE, "shimano-cs-hg500-10-11-34", None, OK),
        (TOPSTONE, "shimano-cs-m4100-11-46", None, NO),  # 46T MTB cassette on a GRX road setup
        (CAAD10, "shimano-cs-5700-12-27", None, OK),
        # Chains: speed, plus the drivetrains that demand a specific chain.
        (SUPERCALIBER, "sram-nx-eagle-chain", None, NO),  # T-Type required
        (SUPERCALIBER, "sram-gx-t-type-chain", None, OK),
        (CHECKPOINT, "sram-rival-flattop-chain", None, OK),
        (CHECKPOINT, "sram-nx-eagle-chain", None, NO),  # Flattop required
        (FUEL_2023, "sram-nx-eagle-chain", None, OK),  # a SRAM chain fits a Shimano 12-speed
        (CAAD10, "sram-pc-1031", None, OK),
        # Derailleurs: shift family (cable pull) and UDH.
        (FUEL_2023, "shimano-rd-m8100-sgs", None, OK),
        (FUEL_2023, "sram-sx-eagle-rd", None, NO),  # SRAM derailleur, Shimano shifters
        (SUPERCALIBER, "sram-gx-t-type-rd", None, OK),
        (MARLIN_2025, "sram-gx-t-type-rd", None, NO),  # needs UDH (and T-Type shifting)
        (CAAD10, "shimano-rd-rx400", None, NO),  # road 10 vs Tiagra 4700/GRX pull
        # Pads: caliper -> pad shape.
        (FUEL_2023, "shimano-d03s-resin", None, OK),
        (FUEL_2023, "shimano-b05s-resin", None, NO),  # 2-piston pad in a 4-piston caliper
        (HIGHTOWER, "sram-g2-metallic", None, OK),
        (CAAD10, "shimano-r55c4-inserts", None, OK),
        (CAAD10, "shimano-d03s-resin", None, NO),  # disc pad on rim brakes
        # Rotors, per wheel: mount and stock size; Shimano 203 is not SRAM 200.
        (FUEL_2023, "shimano-rt66-203-6b", FRONT, OK),
        (FUEL_2023, "shimano-rt66-203-6b", REAR, NO),  # stock rear is 180
        (HIGHTOWER, "shimano-rt66-203-6b", FRONT, NO),  # stock front is 200
        (HIGHTOWER, "sram-centerline-200-6b", FRONT, OK),
        (CHECKPOINT, "shimano-rt66-160-6b", FRONT, NO),  # Center Lock hub
        (CAAD10, "shimano-rt66-160-6b", FRONT, NO),  # rim brakes
        # Bottom brackets: shell and spindle.
        (HIGHTOWER, "sram-dub-bsa", None, OK),
        (HIGHTOWER, "shimano-bb-mt501", None, NO),  # 24 mm BB, DUB crank
        (CAAD10, "fsa-bb30-bearings", None, OK),
        (EMONDA, "wheels-mfg-t47-24", None, OK),
        (EMONDA, "sram-dub-t47", None, NO),
        # Tires, per wheel: the mullet differs front and rear; 700c is 29".
        (SLASH, "maxxis-dhr2-29x2-4", FRONT, OK),
        (SLASH, "maxxis-dhr2-29x2-4", REAR, NO),
        (SLASH, "maxxis-dhr2-27-5x2-4", REAR, OK),
        (CHECKPOINT, "panaracer-gravelking-700x45", FRONT, OK),
        (FUEL_2023, "maxxis-rekon-29x2-6", FRONT, NO),  # 66 mm > 64 mm max
        (FUEL_2012, "maxxis-ardent-26x2-25", FRONT, UNKNOWN),  # max tire not recorded
    ],
)
def test_real_catalog_cases(bike, part, position, expected):
    assert status(bike, part, position) is expected


def test_tube_needs_tire_width():
    assert status(CAAD10, "tube-700x18-25-presta-60", FRONT) is UNKNOWN
    assert status(CAAD10, "tube-700x18-25-presta-60", FRONT, tire_width_mm=23) is OK
    assert status(CAAD10, "tube-700x28-35-presta", FRONT, tire_width_mm=23) is NO


def test_700c_and_29_inch_are_one_size():
    # A "700c" tube in a 29er: same 622 mm bead seat.
    assert status(FUEL_2023, "tube-700x35-45-presta", FRONT, tire_width_mm=40) is OK


# --- Result shape ------------------------------------------------------------------------------


def test_reasons_lead_with_the_deciding_finding():
    # Micro Spline Shimano MTB cassette on the Hightower: wrong freehub AND wrong shifting
    # system, right speed count. Both failures lead; the passing check comes last.
    result = check(BIKES[HIGHTOWER], PARTS["shimano-cs-m7100-10-51"], RULES)
    assert len(result.reasons) == 3
    assert "doesn't fit" in result.reasons[0]
    assert "doesn't match" in result.reasons[1]
    assert "matches the 12-speed" in result.reasons[2]


def test_adapter_reported_only_when_compatible():
    rules = Rules(
        [CompatRule(rule_type="freehub_cassette", bike_value="xdr", part_value="xd",
                    compatible=True, adapter="1.85 mm spacer")]
    )  # fmt: skip
    bike = BIKES[SUPERCALIBER].model_copy(update={"freehub": "xdr"})
    assert check(bike, PARTS["sram-xs-1275-10-52"], rules).requires_adapter == "1.85 mm spacer"
    wrong_speed = bike.model_copy(update={"drivetrain_speeds": 11})
    result = check(wrong_speed, PARTS["sram-xs-1275-10-52"], rules)
    assert (result.status, result.requires_adapter) == (NO, None)


def test_per_wheel_parts_get_one_result_per_wheel():
    results = check_all_positions(BIKES[SLASH], PARTS["maxxis-dhr2-29x2-4"], RULES)
    assert [(r.position, r.status) for r in results] == [(FRONT, OK), (REAR, NO)]
    assert len(check_all_positions(BIKES[SLASH], PARTS["sram-nx-eagle-chain"], RULES)) == 1


def test_position_required_exactly_for_per_wheel_parts():
    with pytest.raises(ValueError):
        check(BIKES[SLASH], PARTS["maxxis-dhr2-29x2-4"], RULES)
    with pytest.raises(ValueError):
        check(BIKES[SLASH], PARTS["sram-nx-eagle-chain"], RULES, FRONT)


# --- Rule-table semantics ----------------------------------------------------------------------


def test_unknown_caliper_is_unknown_not_a_guess():
    bike = BIKES[FUEL_2023].model_copy(update={"brake_caliper": "Hope Tech 4 E4"})
    assert check(bike, PARTS["shimano-d03s-resin"], RULES).status is UNKNOWN


def test_renamed_caliper_without_rules_becomes_unknown():
    # The typo-fix scenario: the bike's caliper name no longer matches any rule.
    bike = BIKES[FUEL_2023].model_copy(update={"brake_caliper": "Shimano Deore M6120, 4-piston"})
    assert check(bike, PARTS["shimano-d03s-resin"], RULES).status is UNKNOWN


def test_unknown_freehub_is_unknown():
    bike = BIKES[CAAD10].model_copy(update={"freehub": "n3w"})
    assert check(bike, PARTS["shimano-cs-5700-12-27"], RULES).status is UNKNOWN


def test_missing_caliper_is_unknown():
    bike = BIKES[FUEL_2023].model_copy(update={"brake_caliper": None})
    assert check(bike, PARTS["shimano-d03s-resin"], RULES).status is UNKNOWN


def test_explicit_cross_family_rule_allows_a_derailleur():
    rules = Rules(
        [*DATA.compat_rules,
         CompatRule(rule_type="shift_family", bike_value="shimano_road_10",
                    part_value="shimano_road_10_4700", compatible=True)]
    )  # fmt: skip
    assert check(BIKES[CAAD10], PARTS["shimano-rd-rx400"], rules).status is OK


# --- Exhaustive: every bike x every part -----------------------------------------------------


def test_every_pair_produces_a_valid_result():
    for bike in BIKES.values():
        for part in PARTS.values():
            for result in check_all_positions(bike, part, RULES, tire_width_mm=40):
                assert result.reasons
                assert (result.position is not None) == (PartCategory(part.category) in PER_WHEEL)
