-- A mechanic can edit a draft's lines before approving it (step 19); record who and when, so
-- "the mechanic had to change the agent's lines" is visible as a signal, not lost.
ALTER TABLE work_orders
    ADD COLUMN edited_by  text,
    ADD COLUMN edited_at  timestamptz,
    -- Public LangSmith link to the run that drafted the order, cached once shared.
    ADD COLUMN trace_url  text,
    ADD CHECK ((edited_by IS NULL) = (edited_at IS NULL));
