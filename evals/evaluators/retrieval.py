"""Retrieval evaluators for the retrieval dataset: any expected chunk counts as a hit."""

from __future__ import annotations

from evals.evaluators import Score

K = 5


def recall_at_k(retrieved: list[str], expected: list[str], k: int = K) -> Score:
    hit = bool(set(retrieved[:k]) & set(expected))
    return Score(
        f"recall_at_{k}", 1.0 if hit else 0.0, "" if hit else f"none of {expected} in top {k}"
    )


def mrr(retrieved: list[str], expected: list[str]) -> Score:
    """1 / rank of the first expected chunk; 0 when none was retrieved."""
    for rank, chunk_id in enumerate(retrieved, start=1):
        if chunk_id in expected:
            return Score("mrr", 1.0 / rank, f"first hit at rank {rank}")
    return Score("mrr", 0.0, "no expected chunk retrieved")
