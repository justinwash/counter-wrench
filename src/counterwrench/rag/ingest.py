"""Sync every chunk into doc_chunks: insert new, re-embed changed, delete removed.

Same idea as `make seed`: the database mirrors the sources, and re-running with nothing
changed embeds nothing.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

import psycopg
from psycopg.rows import dict_row

from counterwrench.catalog import BikeSpec, LaborItem
from counterwrench.db.connection import connect
from counterwrench.rag.chunks import Chunk, bike_chunks, doc_chunks, labor_chunks
from counterwrench.rag.docs import load_docs
from counterwrench.rag.embed import Embedder, default_embedder, to_pgvector


@dataclass
class IngestReport:
    added: int = 0
    updated: int = 0
    removed: int = 0
    unchanged: int = 0

    def __str__(self) -> str:
        return (
            f"{self.added} added, {self.updated} re-embedded, {self.removed} removed, "
            f"{self.unchanged} unchanged"
        )


def build_chunks(conn: psycopg.Connection) -> list[Chunk]:
    """Docs from disk; labor menu and bikes from the database (seeded from data/seed)."""
    cursor = conn.cursor(row_factory=dict_row)
    labor = [
        LaborItem.model_validate(r)
        for r in cursor.execute("SELECT * FROM labor_menu ORDER BY code").fetchall()
    ]
    bikes = [
        BikeSpec.model_validate(r)
        for r in cursor.execute("SELECT * FROM bikes ORDER BY id").fetchall()
    ]
    return doc_chunks(load_docs()) + labor_chunks(labor) + bike_chunks(bikes)


def ingest(conn: psycopg.Connection, chunks: list[Chunk], embedder: Embedder) -> IngestReport:
    """Sync `chunks` into doc_chunks in one transaction."""
    ids = [c.id for c in chunks]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate chunk ids")
    existing = dict(conn.execute("SELECT id, content_hash FROM doc_chunks").fetchall())
    changed = [c for c in chunks if existing.get(c.id) != c.content_hash]
    vectors = embedder.embed_documents([c.text for c in changed]) if changed else []

    report = IngestReport(unchanged=len(chunks) - len(changed))
    with conn.transaction():
        for chunk, vector in zip(changed, vectors, strict=True):
            conn.execute(
                """
                INSERT INTO doc_chunks (id, source, doc_type, title, heading, content,
                                        bike_ids, complaints, content_hash, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector)
                ON CONFLICT (id) DO UPDATE SET
                    source = EXCLUDED.source, doc_type = EXCLUDED.doc_type,
                    title = EXCLUDED.title, heading = EXCLUDED.heading,
                    content = EXCLUDED.content, bike_ids = EXCLUDED.bike_ids,
                    complaints = EXCLUDED.complaints, content_hash = EXCLUDED.content_hash,
                    embedding = EXCLUDED.embedding
                """,
                (
                    chunk.id, chunk.source, chunk.doc_type, chunk.title, chunk.heading,
                    chunk.content, list(chunk.bike_ids), list(chunk.complaints),
                    chunk.content_hash, to_pgvector(vector),
                ),
            )  # fmt: skip
            if chunk.id in existing:
                report.updated += 1
            else:
                report.added += 1
        stale = set(existing) - set(ids)
        for chunk_id in stale:
            conn.execute("DELETE FROM doc_chunks WHERE id = %s", (chunk_id,))
        report.removed = len(stale)
    return report


def main() -> int:
    try:
        with connect(autocommit=True) as conn:
            chunks = build_chunks(conn)
            report = ingest(conn, chunks, default_embedder())
    except psycopg.OperationalError as exc:
        print(f"Can't connect to Postgres ({exc}). Is it running? Try `make up`.")
        return 1
    print(f"doc_chunks           {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
