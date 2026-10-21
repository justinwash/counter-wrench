"""`make prod-harvest`: live orders worth a second look, as a file for Justin to label.

Rejected, edited by the mechanic, thumbs-down or thumbs-up. The output holds what the customer
asked (as stored, after the guardrails) and what the agent produced, with the reason it was
picked and an empty `label`. Nothing here becomes a golden until it is labeled by hand (D-030);
no code loads this file into a dataset. The agent's original lines are not kept once a mechanic
edits them (the drafting trace has them), so "edited" is the signal, not a diff.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from counterwrench.db.connection import connect
from counterwrench.online.ratings import votes_for

ORDERS = """
    SELECT id, created_at, status, severity, customer_explanation, mechanic_notes, intake,
           edited_by, review_notes, draft_run_id, langsmith_run_id
    FROM work_orders
    WHERE source = 'counter' AND intake IS NOT NULL
    ORDER BY created_at
"""


def reasons(order: dict, votes: list) -> list[str]:
    out = []
    if order["status"] == "rejected":
        out.append(f"rejected by the mechanic: {order['review_notes']}")
    if order["edited_by"]:
        out.append(f"edited by {order['edited_by']} before the decision")
    out += [f"thumbs-down from {v.rater}: {v.reason}" for v in votes if v.rating == "down"]
    out += [f"thumbs-up from {v.rater}" for v in votes if v.rating == "up"]
    return out


def harvest(orders: list[dict], votes: dict[int, list], lines: dict[int, list]) -> list[dict]:
    items = []
    for o in orders:
        why = reasons(o, votes.get(o["id"], []))
        if not why:
            continue
        items.append(
            {
                "order_id": o["id"],
                "picked_because": why,
                "safety": o["severity"] == "safety_critical",
                "intake": o["intake"],
                "agent_output": {
                    "severity": o["severity"],
                    "lines": lines.get(o["id"], []),
                    "customer_explanation": o["customer_explanation"],
                    "mechanic_notes": o["mechanic_notes"],
                },
                "trace_run_id": str(o["draft_run_id"] or o["langsmith_run_id"] or ""),
                "label": None,  # Justin fills this in: the right severity, lines and explanation
            }
        )
    items.sort(key=lambda i: (not i["safety"], i["order_id"]))  # safety first
    return items


def main() -> None:
    from psycopg.rows import dict_row

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="harvest.yaml")
    args = parser.parse_args()
    with connect() as conn:
        orders = conn.cursor(row_factory=dict_row).execute(ORDERS).fetchall()
        votes = {o["id"]: votes_for(conn, o["id"]) for o in orders}
        lines: dict[int, list] = {}
        for oid, item, qty in conn.execute(
            "SELECT work_order_id, coalesce(labor_code, part_id), qty "
            "FROM work_order_lines ORDER BY id"
        ):
            lines.setdefault(oid, []).append({"item": item, "qty": qty})
    items = harvest(orders, votes, lines)
    text = yaml.safe_dump(items, sort_keys=False, allow_unicode=True)
    Path(args.out).write_text(text, encoding="utf-8")
    print(f"{len(items)} orders worth labeling -> {args.out}, safety first.")
    print("Nothing was added to any dataset: label them, then add the ones you trust.")


if __name__ == "__main__":
    main()
