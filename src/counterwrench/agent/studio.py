"""Entry point for LangGraph Studio (`make studio`), which supplies its own checkpointer.

Paste a sample from data/samples/ into the `intake` input.
"""

from counterwrench.agent.graph import build_graph

graph = build_graph()
