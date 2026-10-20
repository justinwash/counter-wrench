"""Triage evaluators: per-row severity, agreement with staff, questions, coverage, validity."""

from __future__ import annotations

from evals.evaluators import Catalog, Reference, Score
from evals.run_output import RunOutput


def severity_correct(run: RunOutput, ref: Reference, ctx: Catalog) -> Score:
    wrong = []
    for row_id, exp in ref.rows.items():
        got = run.assessments.get(row_id)
        if got is None or got.severity != exp.severity.value:
            wrong.append(
                f"{row_id}: expected {exp.severity.value}, got {got.severity if got else 'none'}"
            )
    right = len(ref.rows) - len(wrong)
    return Score("severity_correct", right / len(ref.rows), "; ".join(wrong))


def agreement_correct(run: RunOutput, ref: Reference, ctx: Catalog) -> Score:
    """Agreed or disagreed with staff's suspected area as labeled; n/a ("unsure") stays n/a.
    Rows labeled agreement_scored=False (needs an inspection first) aren't scored."""
    rows = {row_id: exp for row_id, exp in ref.rows.items() if exp.agreement_scored}
    if not rows:
        return Score("agreement_correct", None, "agreement not scored for this case")
    wrong = []
    for row_id, exp in rows.items():
        got = run.assessments.get(row_id)
        if got is None or got.agrees != exp.agrees:
            wrong.append(f"{row_id}: expected {exp.agrees}, got {got.agrees if got else 'none'}")
    return Score("agreement_correct", (len(rows) - len(wrong)) / len(rows), "; ".join(wrong))


def clarification_correct(run: RunOutput, ref: Reference, ctx: Catalog) -> Score:
    """Asked exactly when the labels say to. Unneeded questions count as much as missed ones."""
    checks, wrong = 0, []
    for row_id, exp in ref.rows.items():
        asked = bool(run.questions.get(row_id))
        checks += 1
        if asked != exp.question_expected:
            wrong.append(
                f"{row_id}: {'asked an unneeded question' if asked else 'missed a question'}"
            )
    asked_bike = "bike" in run.questions
    checks += 1
    if asked_bike != ref.bike_question_expected:
        wrong.append("bike: " + ("asked unnecessarily" if asked_bike else "didn't ask which bike"))
    return Score("clarification_correct", (checks - len(wrong)) / checks, "; ".join(wrong))


def row_coverage(run: RunOutput, ref: Reference, ctx: Catalog) -> Score:
    expected = set(ref.rows)
    invented = set(run.assessments) - expected
    if invented:
        return Score("row_coverage", 0.0, f"invented rows: {sorted(invented)}")
    covered = expected & set(run.assessments)
    missing = sorted(expected - covered)
    comment = f"no assessment for {missing}" if missing else ""
    return Score("row_coverage", len(covered) / len(expected), comment)


def first_try_valid(run: RunOutput, ref: Reference, ctx: Catalog) -> Score:
    """Triage output valid on the first call. Retries hide weakness behind a correct answer."""
    if run.triage_retries == 0 and not run.failed_rows:
        return Score("first_try_valid", 1.0)
    return Score(
        "first_try_valid",
        0.0,
        f"{run.triage_retries} retries, {len(run.failed_rows)} rows failed",
    )


EVALUATORS = [severity_correct, agreement_correct, clarification_correct, row_coverage,
              first_try_valid]  # fmt: skip
