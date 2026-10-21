-- Online evaluation (step 21).
--
-- A counter order spans several LangSmith traces: triage (langsmith_run_id, which is also the
-- graph's thread id), then the drafting run when staff create the work order. Record the
-- drafting run and keep a public link for each, so a reviewer can open the tool calls too.
ALTER TABLE work_orders
    ADD COLUMN draft_run_id    uuid,
    ADD COLUMN draft_trace_url text;

-- Thumbs up/down on the agent's work, one vote per person per order (changing your vote
-- replaces it). Down needs a reason: it feeds the failure review.
CREATE TABLE order_ratings (
    order_id   bigint NOT NULL REFERENCES work_orders (id) ON DELETE CASCADE,
    rater      text   NOT NULL,
    rating     text   NOT NULL CHECK (rating IN ('up', 'down')),
    reason     text,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (order_id, rater),
    CHECK (rating = 'up' OR coalesce(btrim(reason), '') <> '')
);
