"""What tools need from the outside world, injected so tests can supply their own."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field

import psycopg

from counterwrench.db.connection import connect
from counterwrench.rag.embed import Embedder


@dataclass
class ToolContext:
    # Opens a connection per tool call in production; tests pass their own database.
    connect: Callable[[], AbstractContextManager[psycopg.Connection]] = field(
        default=lambda: connect()
    )
    # None means the real local embedding model (loaded on first search).
    embedder: Embedder | None = None
