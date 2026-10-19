"""The CounterWrench graph, v0 (step 10a: triage).

resolve_bike -> retrieve -> triage_row (one parallel branch per row) -> route.
Step 10b adds draft and human review after route.
"""

from __future__ import annotations

from functools import partial

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from counterwrench.agent.nodes import Deps, resolve_bike, retrieve, route, triage_row
from counterwrench.agent.state import GraphState


def fan_out_rows(state: GraphState) -> list[Send]:
    """One triage branch per complaint row, each with only its own retrieved chunks."""
    return [
        Send(
            "triage_row",
            {
                "intake": state["intake"],
                "bike": state.get("bike"),
                "row_id": row.row_id,
                "chunks": state["row_chunks"][row.row_id],
            },
        )
        for row in state["intake"].rows
    ]


def build_graph(deps: Deps | None = None):
    deps = deps or default_deps()
    graph = StateGraph(GraphState)
    graph.add_node("resolve_bike", partial(resolve_bike, deps=deps))
    graph.add_node("retrieve", partial(retrieve, deps=deps))
    graph.add_node("triage_row", partial(triage_row, deps=deps))
    graph.add_node("route", route)
    graph.add_edge(START, "resolve_bike")
    graph.add_edge("resolve_bike", "retrieve")
    graph.add_conditional_edges("retrieve", fan_out_rows, ["triage_row"])
    graph.add_edge("triage_row", "route")
    graph.add_edge("route", END)
    return graph.compile()


def default_deps(config=None) -> Deps:
    """Real dependencies. Models are built only through config.py, from one loaded config."""
    from counterwrench.config import build_chat_model, load_config

    config = config or load_config()
    return Deps(triage_model=lambda: build_chat_model(config.triage, config))
