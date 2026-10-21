"""The CounterWrench API: a thin layer over the graph, the catalog and the work orders.

    uv run uvicorn counterwrench.api.app:app --reload

`create_app` takes the graph's dependencies, so tests run the real routes with scripted models.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI
from langgraph.checkpoint.memory import InMemorySaver

from counterwrench.agent.graph import build_graph, default_deps
from counterwrench.agent.nodes import Deps


@dataclass
class AppState:
    deps: Deps
    graph: Any
    config: Any = None  # ModelConfig, for run metadata; None in tests


def create_app(deps: Deps | None = None, checkpointer=None, config=None) -> FastAPI:
    from counterwrench.api import catalog, intakes, orders

    if deps is None:
        from counterwrench.config import load_config

        config = config or load_config()
        deps = default_deps(config)
        checkpointer = checkpointer or postgres_checkpointer()
    app = FastAPI(title="CounterWrench", version="0.1.0")
    graph = build_graph(
        deps, checkpointer=checkpointer or InMemorySaver(), confirm_before_draft=True
    )
    app.state.cw = AppState(deps=deps, graph=graph, config=config)
    app.include_router(catalog.router, prefix="/api")
    app.include_router(intakes.router, prefix="/api")
    app.include_router(orders.router, prefix="/api")
    return app


def postgres_checkpointer(url: str | None = None):
    """Paused runs (drafts awaiting review) survive a server restart. LangGraph manages its own
    checkpoint tables; `setup()` creates or migrates them and is safe to run every start."""
    import os

    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    from counterwrench.db.connection import database_url

    pool = ConnectionPool(
        url or database_url(os.environ), open=True,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    )  # fmt: skip
    saver = PostgresSaver(pool)
    saver.setup()
    return saver


def __getattr__(name: str):
    # `uvicorn counterwrench.api.app:app` builds the real app on first access, so importing this
    # module (tests, tooling) never loads models or connects to anything.
    if name == "app":
        return create_app()
    raise AttributeError(name)
