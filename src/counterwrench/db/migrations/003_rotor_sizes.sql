-- Replace the frame's max rotor size with the stock rotor size per wheel. Spec sheets list
-- installed rotors (e.g. 203 mm front, 180 mm rear), rarely a frame maximum, and front and
-- rear commonly differ. Replacement rotors match the stock size unless deliberately upsized.

ALTER TABLE bikes
    ADD COLUMN front_rotor_mm int CHECK (front_rotor_mm > 0),
    ADD COLUMN rear_rotor_mm  int CHECK (rear_rotor_mm > 0);

-- Backfill existing rows before the new rule below, or it would reject them.
UPDATE bikes
SET front_rotor_mm = max_rotor_mm, rear_rotor_mm = max_rotor_mm
WHERE brake_type <> 'rim';

ALTER TABLE bikes
    DROP COLUMN max_rotor_mm,
    -- Disc brakes have a rotor on each wheel; rim brakes have none.
    ADD CHECK ((brake_type = 'rim') = (front_rotor_mm IS NULL)),
    ADD CHECK ((brake_type = 'rim') = (rear_rotor_mm IS NULL));
