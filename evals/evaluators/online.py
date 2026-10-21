"""Checks that need no labeled answer, for scoring live traffic (step 21).

Offline, a case carries a label (the right severity, the right labor); live, nothing does. These
look only at what the system itself produced and at facts it can check independently: the
catalog, the rules, the agent's own triage. They sit next to the offline evaluators and run the
same way, `(run, ref, ctx) -> Score`.
"""

from __future__ import annotations

from counterwrench.models import Severity, max_severity
from evals.evaluators import Catalog, Reference, Score
from evals.evaluators.draft import _pii_in
from evals.run_output import RunOutput


def safety_consistent(run: RunOutput, ref: Reference, ctx: Catalog) -> Score:
    """If triage called any row safety-critical, the whole order says so: escalated at the
    counter, and (once drafted) saved safety-critical with priority set. The live version of
    the offline safety gate, which needs no label because it compares the system with itself."""
    if not run.assessments:
        return Score("safety_consistent", None, "nothing triaged")
    critical = [row for row, a in run.assessments.items() if a.severity == "safety_critical"]
    if not critical:
        return Score("safety_consistent", 1.0)
    problems = []
    if not run.escalated:
        problems.append("triage called a row safety-critical but the run wasn't escalated")
    if run.draft and not (run.draft.severity == "safety_critical" and run.draft.priority):
        problems.append(
            f"order saved as {run.draft.severity} (priority={run.draft.priority}) "
            f"despite safety-critical rows {critical}"
        )
    return Score("safety_consistent", 0.0 if problems else 1.0, "; ".join(problems))


def severity_matches_triage(run: RunOutput, ref: Reference, ctx: Catalog) -> Score:
    """The saved order's severity is the worst of the rows (code sets it: D-028)."""
    if run.draft is None or not run.assessments:
        return Score("severity_matches_triage", None, "no draft")
    worst = max_severity(Severity(a.severity) for a in run.assessments.values()).value
    if run.draft.severity == worst:
        return Score("severity_matches_triage", 1.0)
    return Score(
        "severity_matches_triage", 0.0, f"triage worst {worst}, order {run.draft.severity}"
    )


def questions_resolved(run: RunOutput, ref: Reference, ctx: Catalog) -> Score:
    """Triage never had to give up on a question (D-051). A failure isn't a bug: it's the
    signal that the agent couldn't settle something the counter could not answer."""
    if run.unresolved:
        return Score(
            "questions_resolved", 0.0, f"gave up after two rounds on {sorted(run.unresolved)}"
        )
    return Score("questions_resolved", 1.0)


def no_pii_in_output(run: RunOutput, ref: Reference, ctx: Catalog) -> Score:
    """Nothing the run produced looks like a customer's email, phone, card or named person.
    (Offline, `pii_absent` compares with the raw input; live, the raw input is never kept.)"""
    found = _pii_in(run.model_dump_json())
    return Score(
        "no_pii_in_output",
        0.0 if found else 1.0,
        f"{len(found)} PII-like value(s)" if found else "",
    )
