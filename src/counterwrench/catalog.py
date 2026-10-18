"""Catalog entries as they appear in the seed files (data/seed/*.yaml).

Standards values are enums, so a typo like `Microsplne` fails validation at seed time instead
of silently never matching in the compatibility engine. Part specs differ per category, so
each category has its own model, selected by the `category` field.
"""

from __future__ import annotations

from enum import IntEnum, StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, HttpUrl, model_validator

from counterwrench.models import (
    BikeCategory,
    BrakeType,
    LaborCode,
    RotorMount,
    ShortText,
    Slug,
    Strict,
)

# --- Standards ---------------------------------------------------------------------------------


class WheelSize(IntEnum):
    """ISO bead-seat diameter in mm."""

    ISO_622 = 622  # 700c / 29"
    ISO_584 = 584  # 650b / 27.5"
    ISO_559 = 559  # 26"

    @property
    def label(self) -> str:
        """Every name counter staff and customers use, so the agent never treats 700c and
        29" (or 650b and 27.5") as different sizes."""
        return f"{self.value} mm ({_WHEEL_NAMES[self]})"


_WHEEL_NAMES = {
    WheelSize.ISO_622: '700c / 29"',
    WheelSize.ISO_584: '650b / 27.5"',
    WheelSize.ISO_559: '26"',
}


class BBStandard(StrEnum):
    BSA = "bsa"  # English threaded, 68/73 mm
    T47 = "t47"
    ITALIAN = "italian"
    BB86 = "bb86"  # Shimano press-fit road
    PF92 = "pf92"  # Shimano press-fit MTB (BB92)
    PF30 = "pf30"
    BB30 = "bb30"
    BB386EVO = "bb386evo"


class CrankSpindle(StrEnum):
    HOLLOWTECH_24 = "hollowtech_24"  # Shimano 24 mm
    DUB = "dub"  # SRAM 28.99 mm
    GXP = "gxp"  # SRAM 24/22 mm stepped
    MM30 = "30mm"
    SQUARE_TAPER = "square_taper"


class RearAxle(StrEnum):
    QR_130 = "qr_130"
    QR_135 = "qr_135"
    TA_12X142 = "12x142"
    TA_12X148 = "12x148"  # Boost
    TA_12X157 = "12x157"  # Super Boost


class Freehub(StrEnum):
    HG = "hg"  # Shimano/SRAM HyperGlide, 8-11 speed
    HG_L2 = "hg_l2"  # Shimano 12-speed road
    MICROSPLINE = "microspline"
    XD = "xd"
    XDR = "xdr"
    N3W = "n3w"  # Campagnolo


class ChainType(StrEnum):
    STANDARD = "standard"
    HYPERGLIDE_PLUS = "hyperglide_plus"
    SRAM_FLATTOP = "sram_flattop"
    SRAM_T_TYPE = "sram_t_type"


class DerailleurMount(StrEnum):
    HANGER = "hanger"
    UDH_DIRECT = "udh_direct"  # SRAM Transmission: needs a UDH frame


class DrivetrainSystem(StrEnum):
    SHIMANO_MECHANICAL = "shimano_mechanical"
    SHIMANO_DI2 = "shimano_di2"
    SRAM_MECHANICAL = "sram_mechanical"
    SRAM_AXS = "sram_axs"


class PadCompound(StrEnum):
    RESIN = "resin"
    METALLIC = "metallic"


class Valve(StrEnum):
    PRESTA = "presta"
    SCHRADER = "schrader"


Speeds = Annotated[int, Field(ge=1, le=13)]
PositiveInt = Annotated[int, Field(gt=0)]

# --- Bikes -------------------------------------------------------------------------------------


class Bike(Strict):
    id: Slug
    make: ShortText
    model: ShortText
    year: int = Field(ge=1990, le=2100)
    spec_variant: ShortText | None = None
    variant_note: ShortText | None = None
    category: BikeCategory
    bb_standard: BBStandard
    crank_spindle: CrankSpindle
    rear_axle: RearAxle
    freehub: Freehub
    drivetrain_speeds: Speeds
    udh: bool
    dropper_post: bool
    brake_type: BrakeType
    brake_caliper: ShortText | None = None
    rotor_mount: RotorMount | None = None
    max_rotor_mm: PositiveInt | None = None
    max_tire_mm: PositiveInt | None = None
    front_wheel_bsd_mm: WheelSize
    rear_wheel_bsd_mm: WheelSize
    # Where the specs came from, for fact-checking. Seed files only; not stored in the DB.
    source: HttpUrl

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if (self.brake_type is BrakeType.RIM) != (self.rotor_mount is None):
            raise ValueError("disc brakes need a rotor_mount; rim brakes can't have one")
        if self.spec_variant and not self.variant_note:
            raise ValueError("a spec_variant needs a variant_note saying how to tell it apart")
        return self


# --- Parts: one specs model per category -------------------------------------------------------


class CassetteSpecs(Strict):
    freehub: Freehub
    speeds: Speeds
    smallest_cog: PositiveInt
    largest_cog: PositiveInt

    @model_validator(mode="after")
    def _cog_order(self) -> Self:
        if self.smallest_cog >= self.largest_cog:
            raise ValueError("smallest_cog must be less than largest_cog")
        return self


class ChainSpecs(Strict):
    speeds: Speeds
    chain_type: ChainType


class RearDerailleurSpecs(Strict):
    speeds: Speeds
    mount: DerailleurMount
    max_cog: PositiveInt
    system: DrivetrainSystem


class BrakePadSpecs(Strict):
    pad_shape: ShortText  # manufacturer pad code, e.g. "Shimano D03S"
    compound: PadCompound


class RotorSpecs(Strict):
    mount: RotorMount
    size_mm: PositiveInt


class BottomBracketSpecs(Strict):
    bb_standard: BBStandard
    spindle: CrankSpindle


class TireSpecs(Strict):
    wheel_bsd_mm: WheelSize
    width_mm: PositiveInt
    tubeless_ready: bool


class TubeSpecs(Strict):
    wheel_bsd_mm: WheelSize
    min_width_mm: PositiveInt
    max_width_mm: PositiveInt
    valve: Valve
    valve_length_mm: PositiveInt

    @model_validator(mode="after")
    def _width_range(self) -> Self:
        if self.min_width_mm > self.max_width_mm:
            raise ValueError("min_width_mm can't exceed max_width_mm")
        return self


class _PartBase(Strict):
    id: Slug
    brand: ShortText
    name: ShortText
    price_cents: int = Field(ge=0)


class CassettePart(_PartBase):
    category: Literal["cassette"]
    specs: CassetteSpecs


class ChainPart(_PartBase):
    category: Literal["chain"]
    specs: ChainSpecs


class RearDerailleurPart(_PartBase):
    category: Literal["rear_derailleur"]
    specs: RearDerailleurSpecs


class BrakePadPart(_PartBase):
    category: Literal["brake_pads"]
    specs: BrakePadSpecs


class RotorPart(_PartBase):
    category: Literal["rotor"]
    specs: RotorSpecs


class BottomBracketPart(_PartBase):
    category: Literal["bottom_bracket"]
    specs: BottomBracketSpecs


class TirePart(_PartBase):
    category: Literal["tire"]
    specs: TireSpecs


class TubePart(_PartBase):
    category: Literal["tube"]
    specs: TubeSpecs


Part = Annotated[
    CassettePart
    | ChainPart
    | RearDerailleurPart
    | BrakePadPart
    | RotorPart
    | BottomBracketPart
    | TirePart
    | TubePart,
    Field(discriminator="category"),
]

# --- Rules and labor ---------------------------------------------------------------------------


class CompatRule(Strict):
    rule_type: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")]
    bike_value: ShortText
    part_value: ShortText
    compatible: bool
    adapter: ShortText | None = None
    note: ShortText | None = None

    @model_validator(mode="after")
    def _adapter_only_if_compatible(self) -> Self:
        if self.adapter and not self.compatible:
            raise ValueError("an incompatible pairing can't have an adapter")
        return self


class LaborItem(Strict):
    code: LaborCode
    name: ShortText
    description: ShortText
    category: ShortText
    price_cents: int = Field(ge=0)
    est_minutes: PositiveInt
