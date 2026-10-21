"""`make prod-report`: how the live agent is doing, from the orders and the thumbs.

Counter orders only (the eval and CLI orders are tagged and left out, D-013). The numbers a shop
cares about first: how often the mechanic accepts the draft as written, edits it, or rejects it;
how often the agent escalates; how often staff run out of answers (the question limit, an
unidentified bike). Safety problems are listed first and never averaged into a rate.
Latency, cost and the live scores come from the LangSmith project, when it can be reached.
"""

from __future__ import annotations

import argparse
import os
import sys
import warnings
from collections import Counter
from dataclasses import dataclass, field

from counterwrench.agent.nodes import MAX_QUESTION_ROUNDS
from counterwrench.db.connection import connect
from counterwrench.online.ratings import votes_for

ORDERS = """
    SELECT id, created_at, status, severity, edited_by, review_notes, intake
    FROM work_orders WHERE source = 'counter' ORDER BY created_at
"""
DECIDED = ("approved", "rejected", "completed")


@dataclass
class Summary:
    total: int = 0
    by_status: Counter = field(default_factory=Counter)
    safety_critical: int = 0
    reviewed: int = 0
    approved_as_drafted: int = 0
    edited: int = 0
    question_limit: int = 0
    bike_unconfirmed: int = 0
    up: int = 0
    down: int = 0
    problems: list[dict] = field(default_factory=list)


def summarize(orders: list[dict], votes: dict[int, list]) -> Summary:
    s = Summary()
    for o in orders:
        s.total += 1
        s.by_status[o["status"]] += 1
        critical = o["severity"] == "safety_critical"
        s.safety_critical += critical
        intake = o["intake"] or {}
        rounds = (intake.get("question_rounds") or {}).values()
        s.question_limit += any(r >= MAX_QUESTION_ROUNDS for r in rounds)
        s.bike_unconfirmed += bool(intake.get("bike_unconfirmed"))
        if o["status"] in DECIDED:
            s.reviewed += 1
            s.edited += o["edited_by"] is not None
            s.approved_as_drafted += o["status"] != "rejected" and o["edited_by"] is None
        mine = votes.get(o["id"], [])
        downs = [v for v in mine if v.rating == "down"]
        s.up += len(mine) - len(downs)
        s.down += len(downs)
        why = [f"rejected: {o['review_notes']}"] if o["status"] == "rejected" else []
        why += [f"thumbs-down from {v.rater}: {v.reason}" for v in downs]
        if why:
            s.problems.append({"id": o["id"], "safety": critical, "why": why})
    s.problems.sort(key=lambda p: (not p["safety"], p["id"]))  # safety first
    return s


def pct(n: int, d: int) -> str:
    return f"{n}/{d} ({100 * n / d:.0f}%)" if d else "n/a"


def render(s: Summary, live: dict | None = None) -> str:
    statuses = ", ".join(f"{k} {v}" for k, v in sorted(s.by_status.items()))
    out = ["# CounterWrench production report", "", f"Counter orders: {s.total} ({statuses})"]
    out += ["", "## What mechanics did with the drafts", ""]
    out.append(f"- Approved as drafted: {pct(s.approved_as_drafted, s.reviewed)}")
    out.append(f"- Edited before the decision: {pct(s.edited, s.reviewed)}")
    out.append(f"- Rejected: {pct(s.by_status['rejected'], s.reviewed)}")
    out += ["", "## What the agent did", ""]
    out.append(f"- Escalated as safety-critical: {pct(s.safety_critical, s.total)}")
    out.append(f"- Hit the {MAX_QUESTION_ROUNDS}-question limit: {pct(s.question_limit, s.total)}")
    out.append(f"- Bike left unconfirmed: {pct(s.bike_unconfirmed, s.total)}")
    out.append(f"- Thumbs: {s.up} up, {s.down} down")
    out += ["", "## Live scores, latency and cost (LangSmith)", ""]
    if live is None:
        out.append("Not available (tracing is off, or LangSmith couldn't be reached).")
    else:
        out.append(
            f"- {live['traces']} traces, mean latency {live['latency_s']:.1f}s, "
            f"mean cost ${live['cost']:.4f} per trace"
        )
        out += [f"- {k}: {v:.2f}" for k, v in sorted(live["scores"].items())]
    out += ["", "## Problems (safety first)", ""]
    for p in s.problems:
        out.append(f"- #{p['id']}{' SAFETY' if p['safety'] else ''}: " + "; ".join(p["why"]))
    if not s.problems:
        out.append("None.")
    return "\n".join(out) + "\n"


def live_stats(project: str, limit: int = 100) -> dict | None:
    """Mean latency, cost and online scores over the project's latest root runs (at most 100,
    LangSmith's page size)."""
    try:
        from langsmith import Client

        with (
            warnings.catch_warnings()
        ):  # list_runs is deprecated after 2027-01-31, as in tracing.py
            warnings.simplefilter("ignore", DeprecationWarning)
            runs = list(
                Client().list_runs(
                    project_name=project,
                    is_root=True,
                    limit=limit,
                    select=["start_time", "end_time", "total_cost", "feedback_stats"],
                )
            )
    except Exception as exc:
        print(f"(LangSmith: {exc})", file=sys.stderr)
        return None
    if not runs:
        return None
    done = [r for r in runs if r.end_time and r.start_time]
    seconds = sum((r.end_time - r.start_time).total_seconds() for r in done)
    scores: dict[str, list[float]] = {}
    for r in runs:
        for key, stat in (r.feedback_stats or {}).items():
            if stat.get("avg") is not None:
                scores.setdefault(key, []).append(stat["avg"])
    return {
        "traces": len(runs),
        "latency_s": seconds / max(len(done), 1),
        "cost": sum(float(r.total_cost or 0) for r in runs) / len(runs),
        "scores": {k: sum(v) / len(v) for k, v in scores.items()},
    }


def main() -> None:
    from dotenv import load_dotenv
    from psycopg.rows import dict_row

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--project", default=os.environ.get("LANGSMITH_PROJECT", "counterwrench-prod")
    )
    args = parser.parse_args()
    load_dotenv(override=False)
    with connect() as conn:
        orders = conn.cursor(row_factory=dict_row).execute(ORDERS).fetchall()
        votes = {o["id"]: votes_for(conn, o["id"]) for o in orders}
    print(render(summarize(orders, votes), live_stats(args.project)))


if __name__ == "__main__":
    main()
