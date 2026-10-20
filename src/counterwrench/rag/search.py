"""search_knowledge: vector, full-text, or hybrid (both, fused with Reciprocal Rank Fusion).

Vector search matches meaning ("creaks when I sit down" -> seated-creak section); full-text
matches exact tokens embeddings blur (Micro Spline, BB30, T47, BRAKE-BLEED). Hybrid runs both
and fuses the two rankings by position, so their incomparable scores never need weighting.

Bike-specific chunks (spec sheets) only match searches for that bike; general chunks always do.
"""

from __future__ import annotations

import argparse
import sys
from enum import StrEnum

import psycopg
from psycopg.rows import dict_row
from pydantic import BaseModel

from counterwrench.db.connection import connect
from counterwrench.rag.embed import Embedder, default_embedder, to_pgvector

RRF_K = 60  # standard constant: dampens how much the very top ranks dominate
CANDIDATES = 20  # how many results each method contributes before fusion


class SearchMode(StrEnum):
    VECTOR = "vector"
    FTS = "fts"
    HYBRID = "hybrid"


# v0 baseline uses vector-only; hybrid is a planned, measured improvement (step 17).
DEFAULT_MODE = SearchMode.VECTOR


class SearchHit(BaseModel):
    chunk_id: str
    title: str
    heading: str
    content: str
    score: float


_BIKE_FILTER = "(cardinality(bike_ids) = 0 OR %(bike_id)s = ANY(bike_ids))"


def _vector_ranking(conn, query_vector: list[float], bike_id: str | None, n: int) -> list[str]:
    rows = conn.execute(
        f"SELECT id FROM doc_chunks WHERE {_BIKE_FILTER} "
        "ORDER BY embedding <=> %(v)s::vector LIMIT %(n)s",
        {"v": to_pgvector(query_vector), "bike_id": bike_id, "n": n},
    ).fetchall()
    return [r[0] for r in rows]


def _fts_ranking(conn, query: str, bike_id: str | None, n: int) -> list[str]:
    # OR the query's terms together: plainto_tsquery ANDs them, which drops any chunk missing
    # a single word of a natural-language question.
    rows = conn.execute(
        f"""
        WITH q AS (
            SELECT NULLIF(replace(plainto_tsquery('english', %(q)s)::text, '&', '|'), '')
                   AS text
        )
        SELECT id FROM doc_chunks, q
        WHERE q.text IS NOT NULL AND tsv @@ to_tsquery('english', q.text) AND {_BIKE_FILTER}
        ORDER BY ts_rank_cd(tsv, to_tsquery('english', q.text)) DESC, id
        LIMIT %(n)s
        """,
        {"q": query, "bike_id": bike_id, "n": n},
    ).fetchall()
    return [r[0] for r in rows]


def rrf(rankings: list[list[str]], k: int = RRF_K) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion: each list adds 1 / (k + rank) for every id it contains."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


def search_knowledge(
    conn: psycopg.Connection,
    query: str,
    bike_id: str | None = None,
    k: int = 5,
    mode: SearchMode = DEFAULT_MODE,
    embedder: Embedder | None = None,
) -> list[SearchHit]:
    rankings = []
    if mode in (SearchMode.VECTOR, SearchMode.HYBRID):
        vector = (embedder or default_embedder()).embed_query(query)
        rankings.append(_vector_ranking(conn, vector, bike_id, CANDIDATES))
    if mode in (SearchMode.FTS, SearchMode.HYBRID):
        rankings.append(_fts_ranking(conn, query, bike_id, CANDIDATES))
    ranked = rrf(rankings)[:k]
    if not ranked:
        return []
    rows = (
        conn.cursor(row_factory=dict_row)
        .execute(
            "SELECT id, title, heading, content FROM doc_chunks WHERE id = ANY(%s)",
            ([chunk_id for chunk_id, _ in ranked],),
        )
        .fetchall()
    )
    by_id = {r["id"]: r for r in rows}
    return [
        SearchHit(chunk_id=chunk_id, score=round(score, 5), **{
            key: by_id[chunk_id][key] for key in ("title", "heading", "content")
        })
        for chunk_id, score in ranked
    ]  # fmt: skip


def get_chunks(conn: psycopg.Connection, chunk_ids: list[str]) -> list[SearchHit]:
    """Chunks by id, in the order given (missing ids are skipped). For knowledge that must reach
    the model whatever the query, rather than whatever similarity search ranks highest."""
    rows = conn.execute(
        "SELECT id, title, heading, content FROM doc_chunks WHERE id = ANY(%s)", (chunk_ids,)
    ).fetchall()
    by_id = {r[0]: r for r in rows}
    return [
        SearchHit(
            chunk_id=i, title=by_id[i][1], heading=by_id[i][2], content=by_id[i][3], score=0.0
        )
        for i in chunk_ids
        if i in by_id
    ]


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m counterwrench.rag.search")
    parser.add_argument("query")
    parser.add_argument("--bike", help="catalog bike id")
    parser.add_argument("--mode", choices=[m.value for m in SearchMode], default=DEFAULT_MODE)
    parser.add_argument("-k", type=int, default=5)
    args = parser.parse_args()
    with connect() as conn:
        hits = search_knowledge(conn, args.query, args.bike, args.k, SearchMode(args.mode))
    for i, hit in enumerate(hits, start=1):
        print(f"{i}. {hit.chunk_id}  ({hit.score})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
