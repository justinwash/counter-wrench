"""Graph nodes. Code does everything code can (bike resolution, retrieval, routing,
escalation); the LLM only triages. Dependencies are injected so tests can fake them."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

import psycopg
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from counterwrench.agent.prompt_builder import build_intake_message, label, retrieval_query
from counterwrench.agent.state import GraphState, RowTask
from counterwrench.compat.lookup import load_bike
from counterwrench.db.connection import connect
from counterwrench.models import RowAssessment, Severity
from counterwrench.rag.embed import Embedder
from counterwrench.rag.search import SearchHit, search_knowledge
from counterwrench.taxonomy import SuspectedArea
from counterwrench.tools.bikes import lookup_bike

PROMPTS = Path(__file__).parent / "prompts"
CHUNKS_PER_ROW = 5
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
    # Returns the triage chat model; built only through config.py.
    triage_model: Callable[[], object] | None = None


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
        for row in intake.rows:
            query = retrieval_query(row, bike, intake.answers.get(row.row_id))
            row_chunks[row.row_id] = search_knowledge(
                conn, query, bike.id if bike else None, k=CHUNKS_PER_ROW, embedder=deps.embedder
            )
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


def route(state: GraphState) -> dict:
    """Deterministic: escalation and next step come from the assessments, not the model."""
    assessments = state.get("assessments", {})
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
        return {
            "escalated": True,
            "escalation_message": (
                f"DO NOT RIDE. Safety-critical issue on row {rows}. The bike stays with us until "
                "a mechanic has inspected it."
            ),
            "questions": questions,
            "outcome": "escalated",
        }
    if questions:
        return {"escalated": False, "escalation_message": None, "questions": questions,
                "outcome": "needs_answers"}  # fmt: skip
    if state.get("failed_rows"):
        return {"escalated": False, "escalation_message": None, "questions": {},
                "outcome": "needs_mechanic"}  # fmt: skip
    return {"escalated": False, "escalation_message": None, "questions": {},
            "outcome": "ready_to_draft"}  # fmt: skip
