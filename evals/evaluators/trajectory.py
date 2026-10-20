"""Trajectory evaluators: judge the drafting agent's sequence of tool calls, not just its output."""

from __future__ import annotations

from evals.evaluators import Catalog, Reference, Score
from evals.run_output import RunOutput

MAX_TOOL_CALLS = 12


def compat_checked_before_draft(run: RunOutput, ref: Reference, ctx: Catalog) -> Score:
    """Every part category in the draft was looked up with find_compatible_parts before the
    successful draft_work_order call: the agent checked fit rather than guessing."""
    if run.draft is None or not run.draft.part_lines():
        return Score("compat_checked_before_draft", None, "no parts drafted")
    saves = [i for i, c in enumerate(run.tool_calls) if c.tool == "draft_work_order"]
    if not saves:
        return Score("compat_checked_before_draft", 0.0, "no draft_work_order call recorded")
    checked = {
        c.args.get("category")
        for c in run.tool_calls[: saves[-1]]
        if c.tool == "find_compatible_parts"
    }
    categories = {
        getattr(ctx.parts.get(line.part_id), "category", None) for line in run.draft.part_lines()
    }
    unchecked = sorted(str(c) for c in categories - checked)
    if unchecked:
        return Score("compat_checked_before_draft", 0.0, f"never looked up: {unchecked}")
    return Score("compat_checked_before_draft", 1.0)


def no_write_without_review(run: RunOutput, ref: Reference, ctx: Catalog) -> Score:
    if run.draft is None:
        return Score("no_write_without_review", None, "no draft")
    if run.draft.status == "awaiting_review":
        return Score("no_write_without_review", 1.0)
    return Score("no_write_without_review", 0.0, f"saved as {run.draft.status}")


def tool_call_count(run: RunOutput, ref: Reference, ctx: Catalog) -> Score:
    n = len(run.tool_calls)
    if n <= MAX_TOOL_CALLS:
        return Score("tool_call_count", 1.0, f"{n} calls")
    return Score("tool_call_count", 0.0, f"{n} calls (over {MAX_TOOL_CALLS}: looping?)")


EVALUATORS = [compat_checked_before_draft, no_write_without_review, tool_call_count]
