"""Graph nodes. Code does everything code can (bike resolution, retrieval, routing,
escalation, pricing, the review update); the LLM triages each row and, in the drafting loop,
picks lines with tools. Dependencies are injected so tests can fake them."""

from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from uuid import UUID

import psycopg
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.types import interrupt
from pydantic import ValidationError

from counterwrench.agent.prompt_builder import build_intake_message, label, retrieval_query
from counterwrench.agent.review import ReviewDecision, apply_review
from counterwrench.agent.state import GraphState, RowTask
from counterwrench.compat.lookup import load_bike
from counterwrench.db.connection import connect
from counterwrench.models import RowAssessment, Severity, max_severity
from counterwrench.rag.embed import Embedder
from counterwrench.rag.search import SearchHit, get_chunks, search_knowledge
from counterwrench.taxonomy import SuspectedArea
from counterwrench.tools import make_tools
from counterwrench.tools.bikes import lookup_bike
from counterwrench.tools.context import ToolContext
from counterwrench.tools.work_orders import DraftWorkOrderArgs, draft_work_order

PROMPTS = Path(__file__).parent / "prompts"
CHUNKS_PER_ROW = 5
# Knowledge every row sees, whatever retrieval ranks: the never-release list decides escalation,
# but reads like no single complaint, so similarity search found it for 4 of 63 rows (F-002).
ALWAYS_INCLUDED = ["policy-safety#what-we-never-release"]
MAX_TRIAGE_ATTEMPTS = 2  # first try plus one retry with the error fed back


@cache
def prompt(name: str) -> str:
    return (PROMPTS / f"{name}.md").read_text("utf-8")


@dataclass
class Deps:
    connect: Callable[[], AbstractContextManager[psycopg.Connection]] = field(
        default=lambda: connect()
    )
    embedder: Embedder | None = None  # None: the real local embedding model
    # Return the chat models; built only through config.py.
    triage_model: Callable[[], object] | None = None
    agent_model: Callable[[], object] | None = None


# --- resolve_bike ----------------------------------------------------------------------------


def resolve_bike(state: GraphState, deps: Deps) -> dict:
    """Catalog id from the picker, or lookup_bike on free text. Ambiguity becomes a question
    raised by code (e.g. which Marlin 7 year), not something the model has to notice."""
    intake = state["intake"]
    with deps.connect() as conn:
        if intake.bike_id:
            bike = load_bike(conn, intake.bike_id)
            note = "Catalog bike." if bike else f"Catalog id {intake.bike_id!r} not found."
            return {"bike": bike, "bike_question": None, "bike_note": note}
        result = lookup_bike(conn, intake.bike_freetext or "")
        bike = load_bike(conn, result.bike.bike_id) if result.status == "found" else None
    question = None
    if result.status == "ambiguous":
        options = " or ".join(c.name for c in result.candidates)
        question = f"Which bike is it: {options}?"
    return {"bike": bike, "bike_question": question, "bike_note": result.message}


# --- retrieve --------------------------------------------------------------------------------


def retrieve(state: GraphState, deps: Deps) -> dict:
    intake, bike = state["intake"], state.get("bike")
    row_chunks: dict[str, list[SearchHit]] = {}
    with deps.connect() as conn:
        pinned = get_chunks(conn, ALWAYS_INCLUDED)
        for row in intake.rows:
            query = retrieval_query(row, bike, intake.answers.get(row.row_id))
            hits = search_knowledge(
                conn, query, bike.id if bike else None, k=CHUNKS_PER_ROW, embedder=deps.embedder
            )
            found = {h.chunk_id for h in hits}
            row_chunks[row.row_id] = hits + [c for c in pinned if c.chunk_id not in found]
    return {"row_chunks": row_chunks}


# --- triage_row --------------------------------------------------------------------------------


def _menu_block(deps: Deps) -> tuple[str, set[str]]:
    with deps.connect() as conn:
        rows = conn.execute(
            "SELECT code, name, price_cents FROM labor_menu ORDER BY category, code"
        ).fetchall()
    lines = [f"{code}: {name} (${cents / 100:.2f})" for code, name, cents in rows]
    return "<service_menu>\n" + "\n".join(lines) + "\n</service_menu>", {r[0] for r in rows}


def _knowledge_block(chunks: list[SearchHit]) -> str:
    return "\n".join(
        f'<knowledge chunk_id="{c.chunk_id}">\n{c.title} - {c.heading}\n{c.content}\n</knowledge>'
        for c in chunks
    )


def check_assessment(
    assessment: RowAssessment, row_id: str, menu_codes: set[str], chunk_ids: set[str]
) -> list[str]:
    """Rules the schema can't express: the right row, real labor codes, honest citations."""
    problems = []
    if assessment.row_id != row_id:
        problems.append(f"row_id must be {row_id!r}.")
    unknown = sorted(set(assessment.suggested_labor) - menu_codes)
    if unknown:
        problems.append(f"Labor codes not on the service menu: {unknown}. Use menu codes only.")
    uncited = sorted(set(assessment.citations) - chunk_ids)
    if uncited:
        problems.append(f"Citations not among the provided chunks: {uncited}.")
    return problems


def triage_row(task: RowTask, deps: Deps) -> dict:
    row_id = task["row_id"]
    row = next(r for r in task["intake"].rows if r.row_id == row_id)
    menu, menu_codes = _menu_block(deps)
    chunk_ids = {c.chunk_id for c in task["chunks"]}
    messages = [
        SystemMessage(prompt("triage") + "\n\n" + menu),
        HumanMessage(
            build_intake_message(task["intake"], task["bike"])
            + "\n\n" + _knowledge_block(task["chunks"])
            + f'\n\nAssess row "{row_id}" ({label(row.complaint)}) only.'
        ),
    ]  # fmt: skip
    model = deps.triage_model().with_structured_output(RowAssessment, include_raw=True)

    retries, last_error = 0, ""
    for attempt in range(MAX_TRIAGE_ATTEMPTS):
        result = model.invoke(messages)
        assessment, error = result.get("parsed"), result.get("parsing_error")
        problems = [str(error)] if error else []
        if assessment is not None and not problems:
            problems = check_assessment(assessment, row_id, menu_codes, chunk_ids)
        if not problems:
            if row.suspected_area == SuspectedArea.UNSURE:
                # Staff didn't commit to an area, so agreement doesn't apply. Enforced in code,
                # whatever the model said.
                assessment = assessment.model_copy(
                    update={"agrees_with_suspected_area": None, "disagreement_reason": None}
                )
            return {"assessments": {row_id: assessment}, "triage_retries": retries}
        last_error = "; ".join(problems)
        if attempt + 1 < MAX_TRIAGE_ATTEMPTS:
            retries += 1
            raw = result.get("raw")
            messages = [
                *messages,
                raw if isinstance(raw, AIMessage) else AIMessage(str(raw)),
                HumanMessage(f"That assessment was invalid: {last_error} Return a corrected one."),
            ]
    return {"failed_rows": {row_id: last_error}, "triage_retries": retries}


# --- route ---------------------------------------------------------------------------------------


MANIPULATION_FLAGS = {"instruction_override"}


def route(state: GraphState) -> dict:
    """Deterministic: escalation and next step come from the assessments, not the model.

    Shop policy (Justin): an intake that tries to override the assistant's instructions is
    treated as a safety hazard until a mechanic inspects the bike, whatever the model concluded,
    so every row is raised to safety_critical here, in code."""
    assessments = state.get("assessments", {})
    updates: dict = {}
    if MANIPULATION_FLAGS & set(state.get("guardrail_flags") or []):
        assessments = {
            row_id: a.model_copy(update={"severity": Severity.SAFETY_CRITICAL})
            for row_id, a in assessments.items()
        }
        updates["assessments"] = assessments
    critical = [
        row_id for row_id, a in assessments.items() if a.severity is Severity.SAFETY_CRITICAL
    ]
    questions = {
        row_id: a.question_for_customer
        for row_id, a in assessments.items()
        if a.question_for_customer
    }
    if state.get("bike_question"):
        questions["bike"] = state["bike_question"]

    if critical:
        rows = ", ".join(critical)
        reason = (
            " The intake contained an attempt to override the assistant's instructions."
            if "assessments" in updates
            else ""
        )
        return {
            **updates,
            "escalated": True,
            "escalation_message": (
                f"DO NOT RIDE. Safety-critical issue on row {rows}.{reason} The bike stays with "
                "us until a mechanic has inspected it."
            ),
            "questions": questions,
            "outcome": "escalated",
        }
    # Only an unresolved bike stops the run: without it no part can be checked. Questions about
    # a row go on the draft for the counter to ask (Justin, step 16), instead of blocking it.
    if "bike" in questions:
        return {"escalated": False, "escalation_message": None, "questions": questions,
                "outcome": "needs_answers"}  # fmt: skip
    if state.get("failed_rows"):
        return {"escalated": False, "escalation_message": None, "questions": questions,
                "outcome": "needs_mechanic"}  # fmt: skip
    return {"escalated": False, "escalation_message": None, "questions": questions,
            "outcome": "ready_to_draft"}  # fmt: skip


# --- draft -----------------------------------------------------------------------------------

MAX_DRAFT_STEPS = 10  # model turns; stops a looping model cleanly


def _triage_block(state: GraphState) -> str:
    rows = {
        row_id: a.model_dump(mode="json", exclude_none=True)
        for row_id, a in state.get("assessments", {}).items()
    }
    lines = ["<triage>", json.dumps(rows, indent=1)]
    if state.get("failed_rows"):
        lines.append(
            f"Rows the triage couldn't assess (mechanic review): {sorted(state['failed_rows'])}"
        )
    if state.get("escalation_message"):
        lines.append(state["escalation_message"])
    lines.append("</triage>")
    return "\n".join(lines)


def draft(state: GraphState, deps: Deps) -> dict:
    """Tool-calling loop: the model picks parts and lines; code injects what it must not choose
    (bike, overall severity, intake, trace link) and records every tool call."""
    intake, bike = state["intake"], state.get("bike")
    assessments = state.get("assessments", {})
    severity = max_severity(a.severity for a in assessments.values()) if assessments else None
    failed_note = (
        f"Triage couldn't assess rows {sorted(state['failed_rows'])}: check them in person."
        if state.get("failed_rows")
        else None
    )
    open_questions = {k: v for k, v in (state.get("questions") or {}).items() if k != "bike"}
    questions_note = (
        "Ask the customer before work starts: "
        + " ".join(f"{row_id}: {q}" for row_id, q in sorted(open_questions.items()))
        if open_questions
        else None
    )
    saved: dict = {}

    def save_draft(**kwargs) -> str:
        args = DraftWorkOrderArgs.model_validate(kwargs)
        overrides = {"bike_id": bike.id if bike else None, "bike_freetext": intake.bike_freetext}
        if severity is not None:
            overrides["severity"] = severity
        code_notes = [failed_note, questions_note, state.get("guardrail_note")]
        if any(code_notes):
            overrides["mechanic_notes"] = "\n".join(
                filter(None, [args.mechanic_notes, *code_notes])
            )
        args = args.model_copy(update=overrides)
        run_id = UUID(state["run_id"]) if state.get("run_id") else None
        with deps.connect() as conn:
            result = draft_work_order(
                conn,
                args,
                intake=intake.model_dump(mode="json"),
                langsmith_run_id=run_id,
                source=state.get("source", "counter"),
            )
        if result.status == "saved":
            saved["result"] = result
        return result.model_dump_json(exclude_none=True)

    ctx = ToolContext(connect=deps.connect, embedder=deps.embedder)
    readers = [t for t in make_tools(ctx) if t.name in
               {"find_compatible_parts", "get_labor_item", "search_labor_menu"}]  # fmt: skip
    writer = StructuredTool.from_function(
        save_draft, name="draft_work_order", args_schema=DraftWorkOrderArgs,
        description="Save the draft work order for mechanic review (codes, part ids and "
        "quantities only; prices and total come from the catalog). Lists problems if rejected.",
    )  # fmt: skip
    tools = {t.name: t for t in [*readers, writer]}
    model = deps.agent_model().bind_tools(list(tools.values()))

    bike_line = f"Catalog bike id: {bike.id}" if bike else "Bike not in the catalog: no parts."
    messages = [
        SystemMessage(prompt("draft")),
        HumanMessage(
            build_intake_message(intake, bike) + "\n\n" + _triage_block(state)
            + f"\n\n{bike_line}\nBuild and save the draft work order."
        ),
    ]  # fmt: skip
    trajectory: list[dict] = []
    for _ in range(MAX_DRAFT_STEPS):
        reply = model.invoke(messages)
        messages.append(reply)
        if not reply.tool_calls:
            break
        for call in reply.tool_calls:
            trajectory.append({"tool": call["name"], "args": call["args"]})
            tool = tools.get(call["name"])
            try:
                output = tool.invoke(call["args"]) if tool else f"No tool named {call['name']!r}."
            except (ValidationError, ValueError) as exc:
                output = f"Invalid arguments: {exc}"
            messages.append(ToolMessage(str(output), tool_call_id=call["id"]))
        if saved:
            break

    if saved:
        result = saved["result"]
        return {"draft": result.model_dump(mode="json"), "work_order_id": result.work_order_id,
                "tool_calls": trajectory, "draft_error": None}  # fmt: skip
    return {
        "draft": None, "work_order_id": None, "tool_calls": trajectory, "outcome": "needs_mechanic",
        "draft_error": "The drafting agent ended without a saved draft; a mechanic must write it.",
    }  # fmt: skip


# --- human_review --------------------------------------------------------------------------------


def human_review(state: GraphState, deps: Deps) -> dict:
    """Pause until a mechanic decides. Resume with {"decision", "reviewer", "notes"}."""
    draft_result = state["draft"]
    answer = interrupt(
        {
            "work_order_id": state["work_order_id"],
            "estimate_total": draft_result["estimate_total"],
            "unverified_parts": draft_result.get("unverified_parts", []),
            "escalated": state.get("escalated", False),
            "action": "Approve or reject this draft (rejections need notes).",
        }
    )
    review = ReviewDecision.model_validate(answer)
    with deps.connect() as conn:
        status = apply_review(conn, state["work_order_id"], review)
    return {"review": {**review.model_dump(), "status": status}}
