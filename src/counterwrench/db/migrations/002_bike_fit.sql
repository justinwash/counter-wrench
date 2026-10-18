-- Bike attributes the compatibility engine needs that 001 missed (found while designing the
-- part specs in step 4a). The catalog is rebuilt from seed files, so these are NOT NULL
-- without defaults: seeding fills them, and seed data must state them explicitly.

ALTER TABLE bikes
    -- ISO bead-seat diameter, not a label: 700c and 29" are both 622, 650b and 27.5" are
    -- both 584. Front and rear are separate for mixed-wheel ("mullet") bikes.
    ADD COLUMN front_wheel_bsd_mm int NOT NULL CHECK (front_wheel_bsd_mm IN (622, 584, 559)),
    ADD COLUMN rear_wheel_bsd_mm  int NOT NULL CHECK (rear_wheel_bsd_mm IN (622, 584, 559)),
    -- BB fit depends on the frame's BB standard AND the crank's spindle.
    ADD COLUMN crank_spindle      text NOT NULL,
    -- A seated creak means a dropper service on one bike and a quick adjustment on another.
    ADD COLUMN dropper_post       boolean NOT NULL;
