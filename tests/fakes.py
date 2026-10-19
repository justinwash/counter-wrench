"""Scripted stand-ins for the chat models, so graph paths can be tested without a network."""

import threading

from langchain_core.messages import AIMessage
from pydantic import ValidationError

from counterwrench.models import RowAssessment


class FakeTriage:
    """Stands in for the triage chat model. `scripts` maps row_id to the responses that row's
    calls return, in order: a dict (validated as RowAssessment) or a string (a parse error)."""

    def __init__(self, scripts: dict[str, list]):
        self.scripts = {row_id: list(items) for row_id, items in scripts.items()}
        self.calls: dict[str, list] = {}
        self._lock = threading.Lock()

    def with_structured_output(self, schema, include_raw):
        return self

    def invoke(self, messages):
        row_id = messages[1].content.rsplit('Assess row "', 1)[1].split('"', 1)[0]
        with self._lock:
            self.calls.setdefault(row_id, []).append(messages)
            item = self.scripts[row_id].pop(0)
        if isinstance(item, str):
            return {"raw": AIMessage(item), "parsed": None, "parsing_error": ValueError(item)}
        try:
            parsed = RowAssessment.model_validate(item)
            return {"raw": AIMessage("ok"), "parsed": parsed, "parsing_error": None}
        except ValidationError as exc:
            return {"raw": AIMessage("bad"), "parsed": None, "parsing_error": exc}


class FakeAgent:
    """Stands in for the drafting model. Returns `turns` in order; each turn is a list of
    (tool_name, args) calls, or a string for a final text reply with no tool calls."""

    def __init__(self, turns: list):
        self.turns = list(turns)
        self.calls = 0
        self.bound_tools: list[str] = []

    def bind_tools(self, tools):
        self.bound_tools = [t.name for t in tools]
        return self

    def invoke(self, messages):
        self.calls += 1
        if not self.turns:
            return AIMessage("done")
        turn = self.turns.pop(0)
        if isinstance(turn, str):
            return AIMessage(turn)
        return AIMessage(
            "",
            tool_calls=[
                {"name": name, "args": args, "id": f"call-{self.calls}-{i}"}
                for i, (name, args) in enumerate(turn)
            ],
        )
