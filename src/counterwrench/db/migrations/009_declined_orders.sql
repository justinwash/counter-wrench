-- A customer can decline the recommended service at the counter (step 20). The decline is kept
-- as a record, with who took it and (for safety-critical work) that a waiver was signed, because
-- "we advised against riding it" is exactly what the shop needs to be able to show later.
ALTER TABLE work_orders DROP CONSTRAINT work_orders_status_check;
ALTER TABLE work_orders ADD CONSTRAINT work_orders_status_check CHECK (status IN (
    'draft', 'awaiting_review', 'approved', 'rejected', 'completed', 'declined'));
ALTER TABLE work_orders
    ADD COLUMN waiver_signed boolean NOT NULL DEFAULT false,
    ADD CHECK (status <> 'declined' OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)),
    -- A safety-critical decline without a signed waiver can't be recorded at all.
    ADD CHECK (status <> 'declined' OR severity <> 'safety_critical' OR waiver_signed);
