"""Failing cases go to a LangSmith annotation queue for review (step 16).

One queue item per failing case, not per repetition: the worst repetition goes in, and a
feedback note on it says how many repetitions failed and on what. Safety failures sort first.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from evals.evaluators.safety import EVALUATORS as SAFETY

QUEUE_NAME = "counterwrench-failures"
SAFETY_KEYS = {f.__name__ for f in SAFETY}


@dataclass(frozen=True)
class ScoredRun:
    example_id: str
    case: str  # the dataset's readable id, e.g. s04-fuelex-lever-to-bar
    run_id: str
    scores: dict[str, float | None]

    @property
    def failing(self) -> list[str]:
        return sorted(k for k, v in self.scores.items() if v is not None and v < 1)


@dataclass(frozen=True)
class QueueItem:
    case: str
    run_id: str  # the worst repetition
    failed_runs: int
    total_runs: int
    failing: list[str] = field(default_factory=list)  # across all repetitions

    @property
    def safety(self) -> bool:
        return bool(SAFETY_KEYS & set(self.failing))

    def note(self) -> str:
        kind = "SAFETY. " if self.safety else ""
        return (
            f"{kind}Failed {self.failed_runs}/{self.total_runs} repetitions; this is the worst. "
            f"Failing: {', '.join(self.failing)}"
        )


def select_failures(runs: list[ScoredRun]) -> list[QueueItem]:
    by_case: dict[str, list[ScoredRun]] = defaultdict(list)
    for run in runs:
        by_case[run.case].append(run)
    items = []
    for case, reps in by_case.items():
        failed = [r for r in reps if r.failing]
        if not failed:
            continue
        worst = max(failed, key=lambda r: len(r.failing))  # first on ties
        failing = sorted({k for r in failed for k in r.failing})
        items.append(QueueItem(case, worst.run_id, len(failed), len(reps), failing))
    return sorted(items, key=lambda i: (not i.safety, -i.failed_runs, i.case))


def push(client, items: list[QueueItem], experiment: str) -> str:
    """Add the items to the queue (created on first use); returns the queue id."""
    queue = next(iter(client.list_annotation_queues(name=QUEUE_NAME)), None)
    if queue is None:
        queue = client.create_annotation_queue(
            name=QUEUE_NAME,
            description="Failing eval cases, one per case (worst repetition). Classify the root "
            "cause; for judge failures, record whether the judge was right.",
        )
    for item in items:
        client.create_feedback(
            item.run_id, key="queue_note", comment=f"{experiment}: {item.note()}"
        )
    if items:
        client.add_runs_to_annotation_queue(queue.id, run_ids=[i.run_id for i in items])
    return str(queue.id)
