"""Thumbs up/down on the agent's work (step 21).

Anyone using the app can rate an order once (changing their vote replaces it). The votes live in
Postgres, so the screen can show them; what the votes do in LangSmith follows from the current
votes, not from the click that just happened, so changing your mind leaves things consistent:

  any thumbs-down  -> the drafting run is in the annotation queue `counterwrench-prod-failures`
                      (the reason attached), and is not a candidate
  only thumbs-up   -> the order is a candidate for the golden set (dataset
                      `counterwrench-candidates`), never a golden: goldens are Justin's labels
  each vote        -> a `user_rating` score on the run (1 up, 0 down) with the reason as comment
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Protocol

import psycopg
from psycopg.rows import dict_row

log = logging.getLogger(__name__)

QUEUE = "counterwrench-prod-failures"
CANDIDATES = "counterwrench-candidates"
_NAMESPACE = uuid.UUID("6f4a1c1e-3a52-5d0f-9a1b-7c0c0ffee123")


@dataclass(frozen=True)
class Vote:
    rater: str
    rating: str  # "up" | "down"
    reason: str | None


class Sink(Protocol):
    """What a vote does outside the database. LangSmith in the app; a recorder in tests."""

    def rated(self, run_id: str, vote: Vote) -> None: ...
    def set_queued(self, run_id: str, queued: bool, reasons: list[str]) -> None: ...
    def set_candidate(self, order_id: int, candidate: dict | None) -> None: ...


def votes_for(conn: psycopg.Connection, order_id: int) -> list[Vote]:
    rows = conn.execute(
        "SELECT rater, rating, reason FROM order_ratings WHERE order_id = %s ORDER BY created_at",
        (order_id,),
    ).fetchall()
    return [Vote(*r) for r in rows]


def record_vote(conn: psycopg.Connection, order_id: int, vote: Vote) -> list[Vote]:
    """Save the vote (replacing this rater's earlier one) and return all votes on the order."""
    conn.execute(
        """
        INSERT INTO order_ratings (order_id, rater, rating, reason) VALUES (%s, %s, %s, %s)
        ON CONFLICT (order_id, rater)
        DO UPDATE SET rating = EXCLUDED.rating, reason = EXCLUDED.reason, created_at = now()
        """,
        (order_id, vote.rater, vote.rating, vote.reason),
    )
    return votes_for(conn, order_id)


def candidate_for(conn: psycopg.Connection, order_id: int) -> dict | None:
    """The order as a golden candidate: the intake as it was stored (after the guardrails) and
    what the agent produced. Nothing the customer typed raw."""
    order = (
        conn.cursor(row_factory=dict_row)
        .execute(
            "SELECT severity, customer_explanation, mechanic_notes, intake "
            "FROM work_orders WHERE id = %s",
            (order_id,),
        )
        .fetchone()
    )
    if order is None or order["intake"] is None:
        return None
    lines = conn.execute(
        "SELECT coalesce(labor_code, part_id), qty FROM work_order_lines "
        "WHERE work_order_id = %s ORDER BY id",
        (order_id,),
    ).fetchall()
    return {
        "inputs": {"intake": order["intake"]},
        "outputs": {
            "severity": order["severity"],
            "lines": [{"item": i, "qty": q} for i, q in lines],
            "customer_explanation": order["customer_explanation"],
            "mechanic_notes": order["mechanic_notes"],
        },  # fmt: skip
    }


def sync(
    sink: Sink, order_id: int, run_id: str, votes: list[Vote], latest: Vote, candidate: dict | None
) -> None:
    """Make the outside world match the votes. Best effort: a vote already counts once it is
    in the database, and a LangSmith hiccup shouldn't turn a click into an error."""
    downs = [v for v in votes if v.rating == "down"]
    ups = [v for v in votes if v.rating == "up"]
    reasons = [f"{v.rater}: {v.reason}" for v in downs]
    steps = [
        ("feedback", lambda: sink.rated(run_id, latest)),
        ("queue", lambda: sink.set_queued(run_id, bool(downs), reasons)),
        (
            "candidate",
            lambda: sink.set_candidate(order_id, candidate if ups and not downs else None),
        ),
    ]
    for name, step in steps:
        try:
            step()
        except Exception:
            log.warning("rating sync (%s) failed for order %s", name, order_id, exc_info=True)


class LangSmithSink:
    def __init__(self, client=None):
        from langsmith import Client

        self.client = client or Client()

    def _project(self, run_id: str):
        from counterwrench.tracing import read_run

        return read_run(self.client, run_id).session_id

    def rated(self, run_id: str, vote: Vote) -> None:
        fid = uuid.uuid5(_NAMESPACE, f"rating/{run_id}/{vote.rater}")  # one per person per run
        fields = {"score": 1 if vote.rating == "up" else 0, "comment": vote.reason or ""}
        try:
            self.client.update_feedback(fid, **fields)
        except Exception:
            self.client.create_feedback(
                run_id,
                key="user_rating",
                feedback_id=fid,
                session_id=self._project(run_id),
                source_info={"rater": vote.rater},
                **fields,
            )

    def set_queued(self, run_id: str, queued: bool, reasons: list[str]) -> None:
        queue = next(iter(self.client.list_annotation_queues(name=QUEUE)), None)
        if queued:
            if queue is None:
                queue = self.client.create_annotation_queue(
                    name=QUEUE,
                    description="Live orders someone rated thumbs-down, reason attached. Classify "
                    "the root cause as in step 16.",
                )
            self.client.add_runs_to_annotation_queue(queue.id, run_ids=[run_id])
        elif queue is not None:
            self.client.delete_run_from_annotation_queue(queue.id, run_id=run_id)

    def set_candidate(self, order_id: int, candidate: dict | None) -> None:
        example_id = uuid.uuid5(_NAMESPACE, f"candidate/{order_id}")
        if candidate is None:
            try:
                self.client.delete_example(example_id)
            except Exception:  # not there: nothing to remove
                pass
            return
        if not self.client.has_dataset(dataset_name=CANDIDATES):
            self.client.create_dataset(
                CANDIDATES,
                description="Orders someone gave a thumbs-up. Candidates only: they become goldens "
                "when Justin labels them (D-030).",
            )
        dataset = self.client.read_dataset(dataset_name=CANDIDATES)
        try:
            self.client.update_example(example_id, **candidate)
        except Exception:
            self.client.create_example(
                dataset_id=dataset.id,
                example_id=example_id,
                metadata={"order_id": order_id, "source": "thumbs_up"},
                **candidate,
            )
