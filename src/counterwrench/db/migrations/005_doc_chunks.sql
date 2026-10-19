-- Retrieval chunks: knowledge-base sections plus chunks generated from the labor menu and
-- bike catalog. One row per chunk; ingestion keeps it in sync with the sources.

-- The Docker init script enables this on the main database, but migrations shouldn't depend
-- on that (fresh test databases, managed Postgres).
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE doc_chunks (
    -- "<doc_id>#<anchor>", "labor#<CODE>" or "bike#<bike_id>": stable, so eval datasets
    -- can name the chunk a question should retrieve.
    id           text PRIMARY KEY,
    source       text NOT NULL CHECK (source IN ('doc', 'labor', 'bike')),
    doc_type     text NOT NULL,
    title        text NOT NULL,
    heading      text NOT NULL,
    content      text NOT NULL,
    -- Bike-specific chunks only match searches for that bike; empty means general.
    bike_ids     text[] NOT NULL DEFAULT '{}',
    complaints   text[] NOT NULL DEFAULT '{}',
    -- Re-embed only when the text changes.
    content_hash text NOT NULL,
    -- BAAI/bge-small-en-v1.5 produces 384 dimensions; changing models means a new migration.
    embedding    vector(384) NOT NULL,
    -- Full-text search over the same text, for exact tokens embeddings blur (BB30, T47, codes).
    tsv          tsvector GENERATED ALWAYS AS (
                     to_tsvector('english', title || ' ' || heading || ' ' || content)
                 ) STORED
);

CREATE INDEX doc_chunks_tsv_idx ON doc_chunks USING gin (tsv);
CREATE INDEX doc_chunks_embedding_idx ON doc_chunks USING hnsw (embedding vector_cosine_ops);
