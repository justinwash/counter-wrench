"""The CounterWrench graph, v0.

resolve_bike -> retrieve -> triage_row (one parallel branch per row) -> route
  -> needs_answers: stop (staff answer the questions and re-run)
  -> otherwise: draft (tool-calling agent) -> human_review (pause for a mechanic) -> end
"""

from __future__ import annotations

from functools import partial

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from counterwrench.agent.nodes import (
    Deps,
    draft,
    human_review,
    resolve_bike,
    retrieve,
    route,
    triage_row,
)
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


def after_route(state: GraphState) -> str:
    return END if state["outcome"] == "needs_answers" else "draft"


def after_draft(state: GraphState) -> str:
    return "human_review" if state.get("work_order_id") else END


def build_graph(deps: Deps | None = None, checkpointer=None, interrupt_before=None):
    """`checkpointer` is required to pause for review; LangGraph Studio supplies its own.
    `interrupt_before=["draft"]` stops after triage, e.g. to test or inspect triage alone."""
    deps = deps or default_deps()
    graph = StateGraph(GraphState)
    graph.add_node("resolve_bike", partial(resolve_bike, deps=deps))
    graph.add_node("retrieve", partial(retrieve, deps=deps))
    graph.add_node("triage_row", partial(triage_row, deps=deps))
    graph.add_node("route", route)
    graph.add_node("draft", partial(draft, deps=deps))
    graph.add_node("human_review", partial(human_review, deps=deps))
    graph.add_edge(START, "resolve_bike")
    graph.add_edge("resolve_bike", "retrieve")
    graph.add_conditional_edges("retrieve", fan_out_rows, ["triage_row"])
    graph.add_edge("triage_row", "route")
    graph.add_conditional_edges("route", after_route, ["draft", END])
    graph.add_conditional_edges("draft", after_draft, ["human_review", END])
    graph.add_edge("human_review", END)
    return graph.compile(checkpointer=checkpointer, interrupt_before=interrupt_before)


def default_deps(config=None) -> Deps:
    """Real dependencies. Models are built only through config.py, from one loaded config."""
    from counterwrench.config import build_chat_model, load_config

    config = config or load_config()
    return Deps(
        triage_model=lambda: build_chat_model(config.triage, config),
        agent_model=lambda: build_chat_model(config.agent, config),
    )
