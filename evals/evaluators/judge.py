"""LLM-judge evaluators, for what code can't check (D-033).

Each judge is pass/fail against a versioned rubric in evals/rubrics/, with its reasoning written
before the verdict. The judge sees the intake as the agent saw it: PII redacted and free text in
untrusted tags, so text aimed at the agent can't steer the judge either. Judge errors raise, so
the experiment records them instead of scoring them as a pass or a fail.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import yaml
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from counterwrench.agent.prompt_builder import build_intake_message, escape
from counterwrench.guardrails import apply_guardrails
from evals.evaluators import Catalog, Reference, Score
from evals.run_output import RunOutput

RUBRICS = Path(__file__).resolve().parents[1] / "rubrics"

Evaluator = Callable[[RunOutput, Reference, Catalog], Score]


@dataclass(frozen=True)
class Rubric:
    name: str
    version: int
    text: str


@cache
def load_rubric(name: str) -> Rubric:
    raw = (RUBRICS / f"{name}.md").read_text(encoding="utf-8")
    _, front, text = raw.split("---", 2)
    return Rubric(name, int(yaml.safe_load(front)["version"]), text.strip())


class Verdict(BaseModel):
    reasoning: str = Field(description="Rule by rule where relevant, citing the case.")
    passed: bool = Field(description="True only if every rule in the rubric holds.")


def _ask(model: BaseChatModel, rubric: Rubric, case: str) -> Verdict:
    judge = model.with_structured_output(Verdict)
    return judge.invoke([SystemMessage(rubric.text), HumanMessage(case)])


def _intake(ref: Reference, ctx: Catalog) -> str:
    intake = apply_guardrails(ref.intake).intake
    return build_intake_message(intake, ctx.bikes.get(intake.bike_id or ""))


def _expert(ref: Reference) -> list[str]:
    return [f"<expert_notes>{escape(ref.judge_notes)}</expert_notes>"] if ref.judge_notes else []


def _cents(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def diagnosis_case(row_id: str, run: RunOutput, ref: Reference, ctx: Catalog) -> str:
    a = run.assessments[row_id]
    knowledge = [
        f'<knowledge chunk_id="{c.chunk_id}" heading="{escape(c.heading)}">\n'
        f"{escape(c.content)}\n</knowledge>"
        for c in run.row_chunks.get(row_id, [])
    ] or ["<knowledge>none retrieved</knowledge>"]
    if a.agrees is None:
        agreement = "not applicable (staff picked unsure)"
    elif a.agrees:
        agreement = "agrees"
    else:
        agreement = f"disagrees: {escape(a.disagreement_reason or '(no reason given)')}"
    assessment = [
        f'<assessment row="{row_id}">',
        "likely causes, most likely first:",
        *(f"- {escape(cause)}" for cause in a.likely_causes),
        f"staff suspected area: {agreement}",
        f"question for the customer: {escape(a.question) if a.question else 'none'}",
        "</assessment>",
    ]
    return "\n".join([_intake(ref, ctx), *knowledge, *_expert(ref), *assessment,
                      f'Grade the assessment of row "{row_id}".'])  # fmt: skip


def explanation_case(run: RunOutput, ref: Reference, ctx: Catalog) -> str:
    d = run.draft
    lines = []
    for line in d.lines:
        if line.kind == "labor":
            lines.append(f"- labor {line.code}: {line.qty} x {_cents(line.unit_price_cents)}")
            continue
        name = getattr(ctx.parts.get(line.part_id), "name", line.part_id)
        flag = f" (fit unverified: {line.unverified_reason})" if line.unverified else ""
        lines.append(f"- part {name}: {line.qty} x {_cents(line.unit_price_cents)}{flag}")
    order = [
        f'<order severity="{d.severity}" priority="{str(d.priority).lower()}">',
        *lines,
        f"total: {_cents(d.estimate_total_cents)}",
        "</order>",
        f"<explanation>\n{escape(d.customer_explanation)}\n</explanation>",
    ]
    return "\n".join([_intake(ref, ctx), *order, "Grade the explanation."])


def make_judges(model: BaseChatModel) -> list[Evaluator]:
    """The judge evaluators, bound to a judge model (config role "judge")."""
    diagnosis_rubric = load_rubric("diagnosis_reasonable")
    explanation_rubric = load_rubric("explanation_quality")

    def diagnosis_reasonable(run: RunOutput, ref: Reference, ctx: Catalog) -> Score:
        meta = {"rubric_version": diagnosis_rubric.version}
        rows = [row_id for row_id in ref.rows if row_id in run.assessments]
        if not rows:
            return Score("diagnosis_reasonable", None, "no assessments", meta)
        verdicts = {row_id: _ask(model, diagnosis_rubric, diagnosis_case(row_id, run, ref, ctx))
                    for row_id in rows}  # fmt: skip
        passed = sum(v.passed for v in verdicts.values())
        comment = "\n".join(
            f"{row_id}: {'PASS' if v.passed else 'FAIL'}. {v.reasoning}"
            for row_id, v in verdicts.items()
        )
        return Score("diagnosis_reasonable", passed / len(rows), comment, meta)

    def explanation_quality(run: RunOutput, ref: Reference, ctx: Catalog) -> Score:
        meta = {"rubric_version": explanation_rubric.version}
        if run.draft is None:
            return Score("explanation_quality", None, "no draft", meta)
        if not run.draft.customer_explanation.strip():
            return Score("explanation_quality", 0.0, "no customer explanation", meta)
        verdict = _ask(model, explanation_rubric, explanation_case(run, ref, ctx))
        return Score("explanation_quality", float(verdict.passed), verdict.reasoning, meta)

    return [diagnosis_reasonable, explanation_quality]
