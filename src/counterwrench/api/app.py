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


def create_app(
    deps: Deps | None = None, checkpointer=None, config=None, rate_limit_per_hour: int | None = None
) -> FastAPI:
    from counterwrench.api import catalog, intakes, limits, orders

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
    limits.install(app, rate_limit_per_hour)
    app.include_router(catalog.router, prefix="/api")
    app.include_router(intakes.router, prefix="/api")
    app.include_router(orders.router, prefix="/api")
    _serve_ui(app)
    return app


def _serve_ui(app: FastAPI) -> None:
    """Serve the built UI from the same port (the Docker image sets CW_STATIC_DIR). Any path
    that isn't the API or a file gets index.html, so deep links like /orders/12 work."""
    import os
    from pathlib import Path

    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    static = Path(os.environ.get("CW_STATIC_DIR", ""))
    if not os.environ.get("CW_STATIC_DIR") or not (static / "index.html").exists():
        return  # development: Vite serves the UI
    app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def ui(path: str):
        if path.startswith("api/"):
            from fastapi import HTTPException

            raise HTTPException(404)
        file = static / path
        return FileResponse(file if path and file.is_file() else static / "index.html")


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
