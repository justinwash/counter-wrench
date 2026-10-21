"""Online evaluation (step 21): score live traffic with the same code as the offline evals.

After triage finishes, and again after a work order is drafted, the app scores that run in a
background thread and attaches the results to its LangSmith trace as feedback, next to the
mechanic's decisions and the thumbs. LangSmith's own online evaluators can't run our code (they
live inside LangSmith, with no access to the catalog or the compatibility engine), so the scoring
happens here and shows up there the same way.

Two stages, because the work is two traces (D-052):
  triage  the triage run: structure checks, the safety check, the diagnosis judge
  draft   the drafting run: parts, prices, coherence, the agent's tool calls, the explanation judge
Judges run on a configurable share of runs (CW_JUDGE_SAMPLE, default all of them).
"""

from __future__ import annotations

import logging
import os
import random
import threading
from collections.abc import Callable

from counterwrench.models import IntakeForm, Severity
from evals.build_output import build_run_output
from evals.datasets.schema import RowExpectation
from evals.evaluators import Reference, Score, load_catalog, trajectory, triage
from evals.evaluators import draft as draft_evals
from evals.evaluators import online as live
from evals.run_output import RunOutput

log = logging.getLogger(__name__)

TRIAGE_CHECKS = [triage.first_try_valid, triage.row_coverage, live.safety_consistent,
                 live.questions_resolved]  # fmt: skip
DRAFT_CHECKS = [
    draft_evals.parts_all_compatible, draft_evals.prices_match_catalog, draft_evals.line_coherence,
    draft_evals.triage_labor_carried, trajectory.compat_checked_before_draft,
    trajectory.no_write_without_review, trajectory.tool_call_count, live.safety_consistent,
    live.severity_matches_triage, live.no_pii_in_output,
]  # fmt: skip
JUDGE_FOR_STAGE = {"triage": "diagnosis_reasonable", "draft": "explanation_quality"}


def reference_for(intake: IntakeForm) -> Reference:
    """A reference with no answers in it: the checks that run live look only at the run and the
    intake. Rows exist so the checks that iterate rows can; their expectations are never read."""
    rows = {r.row_id: RowExpectation(severity=Severity.NO_ACTION_NEEDED, agrees=None)
            for r in intake.rows}  # fmt: skip
    return Reference(intake=intake, rows=rows, escalation_required=False,
                     bike_question_expected=False, order_expected=True)  # fmt: skip


def judge_sample_rate(env: dict | None = None) -> float:
    raw = (env if env is not None else os.environ).get("CW_JUDGE_SAMPLE", "1")
    try:
        return min(1.0, max(0.0, float(raw)))
    except ValueError:
        return 1.0


class OnlineScorer:
    """`post(run_id, scores)` delivers the scores (LangSmith feedback in the app; a list in
    tests). `judges` is a callable returning {judge name: evaluator}, built on first use so the
    judge model isn't loaded until a judge is actually due."""

    def __init__(
        self,
        connect: Callable,
        post: Callable[[str, list[Score]], None],
        judges: Callable[[], dict[str, Callable]] | None = None,
        judge_rate: float = 1.0,
        rng: Callable[[], float] = random.random,
        background: bool = True,
    ):
        self.connect, self.post, self.judge_rate, self.rng = connect, post, judge_rate, rng
        self._judge_factory, self._judges, self.background = judges, None, background
        self._lock = threading.Lock()

    def judges(self) -> dict[str, Callable]:
        with self._lock:
            if self._judges is None:
                self._judges = self._judge_factory() if self._judge_factory else {}
            return self._judges

    def scores_for(self, stage: str, out: RunOutput, intake: IntakeForm) -> list[Score]:
        ref, ctx = reference_for(intake), load_catalog()
        checks = TRIAGE_CHECKS if stage == "triage" else DRAFT_CHECKS
        scores = [check(out, ref, ctx) for check in checks]
        judge = self.judges().get(JUDGE_FOR_STAGE[stage])
        if judge is not None and self.rng() < self.judge_rate:
            try:
                scores.append(judge(out, ref, ctx))
            except Exception:  # a judge failing must not lose the other scores
                log.warning("online judge %s failed", JUDGE_FOR_STAGE[stage], exc_info=True)
        return [s for s in scores if s.score is not None]  # None means "not applicable here"

    def score(self, stage: str, run_id: str, values: dict) -> list[Score]:
        with self.connect() as conn:
            out = build_run_output(values, conn)
        scores = self.scores_for(stage, out, values["intake"])
        self.post(run_id, scores)
        return scores

    def schedule(self, stage: str, run_id: str, values: dict) -> threading.Thread | None:
        """Score without holding up the response. Never raises: scoring is best effort."""

        def work() -> None:
            try:
                self.score(stage, run_id, values)
            except Exception:
                log.warning("online scoring failed for %s run %s", stage, run_id, exc_info=True)

        if not self.background:
            work()
            return None
        thread = threading.Thread(target=work, name=f"online-{stage}", daemon=True)
        thread.start()
        return thread


def post_to_langsmith(run_id: str, scores: list[Score]) -> None:
    """Attach the scores to the run's trace. Waits for the run to arrive first: traces upload
    in the background, a moment after the response."""
    from counterwrench.tracing import wait_for_run

    found = wait_for_run(run_id, timeout_s=90)
    if not found:
        log.warning("run %s never reached LangSmith; scores dropped", run_id)
        return
    client, run = found
    for s in scores:
        client.create_feedback(
            run_id,
            key=s.key,
            score=s.score,
            comment=(s.comment or None),
            session_id=run.session_id,
            source_info={"online": True, **s.metadata},
        )


def build_scorer(config, connect, judge_rate: float | None = None) -> OnlineScorer:
    """The scorer the running app uses: posts to LangSmith, judges with the configured judge."""
    from counterwrench.config import build_chat_model
    from evals.evaluators.judge import make_judges

    def judges() -> dict[str, Callable]:
        return {j.__name__: j for j in make_judges(build_chat_model(config.judge, config))}

    return OnlineScorer(
        connect=connect,
        post=post_to_langsmith,
        judges=judges,
        judge_rate=judge_sample_rate() if judge_rate is None else judge_rate,
    )
