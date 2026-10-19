-- Work orders: the agent's only write. Drafts land in awaiting_review; a human reviews them.
-- Guarantees live here as well as in the tool, so even a bug in our code can't break them.

CREATE TABLE work_orders (
    id                   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    created_at           timestamptz NOT NULL DEFAULT now(),
    status               text NOT NULL DEFAULT 'awaiting_review' CHECK (status IN (
                             'draft', 'awaiting_review', 'approved', 'rejected', 'completed')),
    -- Foreign keys: a draft can't reference a bike, part or code that doesn't exist, and
    -- `make seed` can't delete one an order uses (it fails and rolls back).
    bike_id              text REFERENCES bikes (id),
    bike_freetext        text,
    severity             text NOT NULL CHECK (severity IN (
                             'safety_critical', 'needs_service', 'needs_adjustment',
                             'cosmetic', 'no_action_needed')),
    -- Safety-critical orders sort first in the review queue without anyone remembering to.
    priority             boolean GENERATED ALWAYS AS (severity = 'safety_critical') STORED,
    customer_explanation text NOT NULL,
    mechanic_notes       text,
    citations            text[] NOT NULL DEFAULT '{}',
    -- Computed in code from catalog prices (D-012), never supplied by the model.
    estimate_total_cents int NOT NULL CHECK (estimate_total_cents >= 0),
    intake               jsonb,
    langsmith_run_id     uuid,
    reviewed_by          text,
    reviewed_at          timestamptz,
    review_notes         text,
    CHECK (bike_id IS NOT NULL OR bike_freetext IS NOT NULL),
    -- No approval, rejection or completion without a human review record.
    CHECK (status NOT IN ('approved', 'rejected', 'completed')
           OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL))
);

CREATE INDEX work_orders_review_queue_idx ON work_orders (status, priority DESC, created_at);

CREATE TABLE work_order_lines (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    work_order_id    bigint NOT NULL REFERENCES work_orders (id) ON DELETE CASCADE,
    labor_code       text REFERENCES labor_menu (code),
    part_id          text REFERENCES parts (id),
    qty              int NOT NULL CHECK (qty BETWEEN 1 AND 10),
    -- The catalog price when drafted; later price changes don't rewrite old estimates.
    unit_price_cents int NOT NULL CHECK (unit_price_cents >= 0),
    position         text CHECK (position IN ('front', 'rear')),
    -- A part whose fit couldn't be confirmed, and why (shown to the reviewing mechanic).
    unverified        boolean NOT NULL DEFAULT false,
    unverified_reason text,
    CHECK ((labor_code IS NULL) <> (part_id IS NULL)),
    CHECK (unverified = (unverified_reason IS NOT NULL)),
    CHECK (NOT unverified OR part_id IS NOT NULL)
);
