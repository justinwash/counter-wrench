-- The mechanic's decision resumes the paused graph as a third LangSmith trace (after triage and
-- drafting). Record it and keep a public link, so the order can show where the run stopped for
-- review and where it continued.
ALTER TABLE work_orders
    ADD COLUMN review_run_id    uuid,
    ADD COLUMN review_trace_url text;
