-- Catalog tables used by seeding (step 4) and the compatibility engine (step 5).
-- Standards values (BB, axle, freehub, caliper) are free text here and validated by
-- Pydantic at seed time; only small, stable value sets get CHECK constraints.

CREATE TABLE bikes (
    -- Stable slug: eval datasets reference bikes by ID, so IDs must survive reseeding.
    id                text PRIMARY KEY CHECK (id ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
    make              text NOT NULL,
    model             text NOT NULL,
    year              int  NOT NULL CHECK (year BETWEEN 1990 AND 2100),
    -- Mid-year spec change: same make/model/year, two rows with different variants.
    spec_variant      text,
    variant_note      text,
    category          text NOT NULL CHECK (category IN ('road', 'gravel', 'mtb', 'commuter')),
    bb_standard       text NOT NULL,
    rear_axle         text NOT NULL,
    freehub           text NOT NULL,
    drivetrain_speeds int  NOT NULL CHECK (drivetrain_speeds BETWEEN 1 AND 13),
    -- Universal Derailleur Hanger: SRAM Transmission (T-Type) rear derailleurs mount
    -- directly to the frame and only fit UDH frames. No default: seed data must say.
    udh               boolean NOT NULL,
    brake_type        text NOT NULL CHECK (brake_type IN ('rim', 'mech_disc', 'hydraulic_disc')),
    brake_caliper     text,
    rotor_mount       text CHECK (rotor_mount IN ('6-bolt', 'centerlock')),
    max_rotor_mm      int  CHECK (max_rotor_mm > 0),
    max_tire_mm       int  CHECK (max_tire_mm > 0),
    -- Disc brakes need a rotor mount; rim brakes can't have one.
    CHECK ((brake_type = 'rim') = (rotor_mount IS NULL)),
    -- A variant must say how to tell it apart from its sibling.
    CHECK (spec_variant IS NULL OR variant_note IS NOT NULL),
    -- NULLS NOT DISTINCT: two rows with no variant still count as duplicates.
    UNIQUE NULLS NOT DISTINCT (make, model, year, spec_variant)
);

CREATE TABLE parts (
    id          text PRIMARY KEY CHECK (id ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
    category    text NOT NULL CHECK (category IN (
                    'cassette', 'chain', 'rear_derailleur', 'brake_pads',
                    'rotor', 'bottom_bracket', 'tire', 'tube')),
    brand       text NOT NULL,
    name        text NOT NULL,
    -- Money is integer cents everywhere; floats can't represent most decimal prices exactly.
    price_cents int  NOT NULL CHECK (price_cents >= 0),
    -- Category-specific attributes (freehub, speeds, mount, size...), validated by a
    -- Pydantic model per category before insert.
    specs       jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(specs) = 'object')
);
CREATE INDEX parts_category_idx ON parts (category);

-- Data-driven compatibility: e.g. ('freehub_cassette', 'XDR', 'XD', true, '1.85 mm spacer').
-- The engine's logic is code; which values fit which is data.
CREATE TABLE compat_rules (
    rule_type  text    NOT NULL,
    bike_value text    NOT NULL,
    part_value text    NOT NULL,
    compatible boolean NOT NULL,
    adapter    text,
    note       text,
    PRIMARY KEY (rule_type, bike_value, part_value),
    CHECK (compatible OR adapter IS NULL)
);

CREATE TABLE labor_menu (
    code        text PRIMARY KEY CHECK (code ~ '^[A-Z0-9]+(-[A-Z0-9]+)*$'),
    name        text NOT NULL,
    description text NOT NULL,
    category    text NOT NULL,
    price_cents int  NOT NULL CHECK (price_cents >= 0),
    est_minutes int  NOT NULL CHECK (est_minutes > 0)
);

CREATE TABLE complaint_taxonomy (
    complaint      text NOT NULL,
    suspected_area text NOT NULL,
    PRIMARY KEY (complaint, suspected_area)
);
