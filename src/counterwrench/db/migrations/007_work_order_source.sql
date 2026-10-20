-- Where an order came from, so eval and CLI drafts can be filtered out of the real queue
-- (WHERE source = 'counter'). Set by code from the caller, never by the model.
ALTER TABLE work_orders
    ADD COLUMN source text NOT NULL DEFAULT 'counter' CHECK (source IN ('counter', 'cli', 'eval'));
