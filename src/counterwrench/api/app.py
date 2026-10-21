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
    online: Any = None  # OnlineScorer, or None when live scoring is off
    ratings: Any = None  # where thumbs go in LangSmith (online/ratings.py), or None


def create_app(
    deps: Deps | None = None,
    checkpointer=None,
    config=None,
    rate_limit_per_hour: int | None = None,
    online=None,
    ratings=None,
) -> FastAPI:
    from counterwrench.api import catalog, intakes, limits, orders

    if deps is None:
        from counterwrench.config import load_config

        config = config or load_config()
        deps = default_deps(config)
        checkpointer = checkpointer or postgres_checkpointer()
        if online is None and live_scoring_enabled():
            from counterwrench.online.scoring import build_scorer

            online = build_scorer(config, deps.connect)
        if ratings is None and live_scoring_enabled():
            from counterwrench.online.ratings import LangSmithSink

            ratings = LangSmithSink()
    app = FastAPI(title="CounterWrench", version="0.1.0")
    graph = build_graph(
        deps, checkpointer=checkpointer or InMemorySaver(), confirm_before_draft=True
    )
    app.state.cw = AppState(deps=deps, graph=graph, config=config, online=online, ratings=ratings)
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


def live_scoring_enabled() -> bool:
    """On when traces are going to LangSmith (that's where the scores go), unless switched off."""
    import os

    return os.environ.get("LANGSMITH_TRACING") == "true" and os.environ.get("CW_ONLINE_EVAL") != "0"


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
