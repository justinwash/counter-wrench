"""Text embeddings: fastembed locally (no API key, deterministic), plus a fake for tests."""

from __future__ import annotations

import hashlib
import math
import re
from functools import cache
from typing import Protocol

MODEL_NAME = "BAAI/bge-small-en-v1.5"
DIM = 384  # must match vector(384) in 005_doc_chunks.sql


class Embedder(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


class FastEmbedder:
    """BGE needs different handling for queries vs passages; fastembed's query_embed and
    embed apply it, so callers must use the matching method."""

    def __init__(self, model_name: str = MODEL_NAME):
        from fastembed import TextEmbedding  # slow import; only when actually embedding

        self._model = TextEmbedding(model_name)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [vector.tolist() for vector in self._model.embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        return next(iter(self._model.query_embed([text]))).tolist()


@cache
def default_embedder() -> FastEmbedder:
    return FastEmbedder()


class FakeEmbedder:
    """Deterministic bag-of-words hashing into DIM buckets: shared words give similar vectors.
    Lets tests exercise ingestion and vector search offline and fast."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    @staticmethod
    def _vector(text: str) -> list[float]:
        vector = [0.0] * DIM
        for word in re.findall(r"[a-z0-9]+", text.lower()):
            vector[int(hashlib.md5(word.encode()).hexdigest(), 16) % DIM] += 1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]


def to_pgvector(vector: list[float]) -> str:
    """pgvector's text format, cast with ::vector in SQL (avoids a numpy adapter dependency)."""
    return "[" + ",".join(f"{v:.7f}" for v in vector) + "]"
