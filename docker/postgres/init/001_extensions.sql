-- One-time setup on an empty data volume. Schema lives in migrations (step 3), not here,
-- because init scripts don't re-run against an existing database.
CREATE EXTENSION IF NOT EXISTS vector;
