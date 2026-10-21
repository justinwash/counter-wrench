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
    from counterwrench.api import catalog, intakes

    if deps is None:
        from counterwrench.config import load_config

        config = config or load_config()
        deps = default_deps(config)
    app = FastAPI(title="CounterWrench", version="0.1.0")
    graph = build_graph(deps, checkpointer=checkpointer or InMemorySaver())
    app.state.cw = AppState(deps=deps, graph=graph, config=config)
    app.include_router(catalog.router, prefix="/api")
    app.include_router(intakes.router, prefix="/api")
    return app


def __getattr__(name: str):
    # `uvicorn counterwrench.api.app:app` builds the real app on first access, so importing this
    # module (tests, tooling) never loads models or connects to anything.
    if name == "app":
        return create_app()
    raise AttributeError(name)
