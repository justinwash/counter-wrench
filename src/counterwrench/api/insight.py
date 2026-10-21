"""Read-only views into how the system is measured and how it decides (step 21b).

    GET /evals/results        every experiment re-scored on today's labels (a committed snapshot)
    GET /evals/calibration    the judges against Justin's blind grades: kappa, confusion matrices
    GET /explore/search       retrieval: the ranked knowledge chunks for a query
    GET /explore/compat       the compatibility engine's verdict for a bike and a part
    GET /orders/{id}/scores   the live scores LangSmith holds for an order's two runs

The eval pages read files in the repo, so they work on a fresh clone with no LangSmith key; only
the live scores need LangSmith, and they say so when it isn't available.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

import evals
from counterwrench.compat.engine import check_all_positions
from counterwrench.compat.lookup import load_bike, load_part, load_rules
from counterwrench.models import CompatResult, PartCategory
from counterwrench.rag.search import SearchHit, SearchMode, search_knowledge
from counterwrench.tools.bikes import _name as bike_name
from evals.calibration.agreement import HERE, LABELS_FILE, SET_FILE, metrics

log = logging.getLogger(__name__)
router = APIRouter(tags=["insight"])

# Next to the evals package wherever it is imported from (the repo, or /app in the image).
SNAPSHOT = Path(evals.__file__).resolve().parent / "snapshot" / "results.json"
JUDGES = ("diagnosis_reasonable", "explanation_quality")
SPLITS = ("dev", "heldout")
# What each set of verdicts is. v2 is what the experiments used; v3 is the recalibrated rubric.
VERDICT_SETS = [
    ("v2", None, "Rubric v2 (used in E-001 to E-007)"),
    ("v3", HERE / "verdicts_v3.json", "Rubric v3 (tuned on the dev split only)"),
]


@router.get("/evals/results")
def results() -> dict[str, Any]:
    """The snapshot written by `make evals-snapshot`: every experiment, every evaluator by
    slice (mean and run-to-run spread), the severity confusion matrix, the safety misses."""
    if not SNAPSHOT.exists():
        raise HTTPException(404, "No results snapshot yet: run `make evals-snapshot`.")
    return json.loads(SNAPSHOT.read_text("utf-8"))


class Metrics(BaseModel):
    n: int
    accuracy: float | None
    tpr: float | None
    tnr: float | None
    kappa: float | None


class Confusion(BaseModel):
    """Rows are Justin's blind grade, columns are the judge's."""

    pass_pass: int
    pass_fail: int  # Justin passed it, the judge failed it
    fail_pass: int  # Justin failed it, the judge passed it
    fail_fail: int


class SplitResult(BaseModel):
    split: str
    metrics: Metrics
    confusion: Confusion


class JudgeResult(BaseModel):
    judge: str
    splits: list[SplitResult]


class RubricResult(BaseModel):
    version: str
    label: str
    judges: list[JudgeResult]


class Verdict(BaseModel):
    verdict: str
    comment: str


class CalibrationItem(BaseModel):
    id: str
    judge: str
    case: str
    slice: str
    split: str
    justin: str
    justin_reason: str | None
    verdicts: dict[str, Verdict]  # by rubric version
    intake: dict[str, Any]
    output: Any


class Calibration(BaseModel):
    experiment: str
    n_items: int
    justin_passed: int
    justin_failed: int
    rubrics: list[RubricResult]
    items: list[CalibrationItem]


def _confusion(pairs: list[tuple[str, str]]) -> Confusion:
    return Confusion(
        pass_pass=pairs.count(("pass", "pass")), pass_fail=pairs.count(("pass", "fail")),
        fail_pass=pairs.count(("fail", "pass")), fail_fail=pairs.count(("fail", "fail")),
    )  # fmt: skip


@router.get("/evals/calibration")
def calibration() -> Calibration:
    """How well each LLM judge agrees with Justin's blind pass/fail grades on 40 outputs."""
    data = json.loads(SET_FILE.read_text("utf-8"))
    labels = json.loads(LABELS_FILE.read_text("utf-8"))["labels"]
    items = [i for i in data["items"] if i["id"] in labels]
    verdicts: dict[str, dict[str, Verdict]] = {i["id"]: {} for i in items}
    for version, path, _ in VERDICT_SETS:
        recorded = json.loads(path.read_text("utf-8"))["verdicts"] if path else None
        for i in items:
            source = recorded[i["id"]] if recorded else {"verdict": i["judge_verdict"],
                                                         "comment": i["judge_comment"]}  # fmt: skip
            verdicts[i["id"]][version] = Verdict(verdict=source["verdict"],
                                                 comment=source.get("comment") or "")  # fmt: skip
    rubrics = []
    for version, _, label in VERDICT_SETS:
        judges = []
        for judge in JUDGES:
            splits = []
            for split in SPLITS:
                pairs = [(labels[i["id"]]["verdict"], verdicts[i["id"]][version].verdict)
                         for i in items if i["judge"] == judge and i["split"] == split]  # fmt: skip
                splits.append(SplitResult(split=split, metrics=Metrics(**metrics(pairs)),
                                          confusion=_confusion(pairs)))  # fmt: skip
            judges.append(JudgeResult(judge=judge, splits=splits))
        rubrics.append(RubricResult(version=version, label=label, judges=judges))
    graded = [labels[i["id"]]["verdict"] for i in items]
    return Calibration(
        experiment=data["experiment"], n_items=len(items),
        justin_passed=graded.count("pass"), justin_failed=graded.count("fail"), rubrics=rubrics,
        items=[CalibrationItem(
            id=i["id"], judge=i["judge"], case=i["case"], slice=i["slice"], split=i["split"],
            justin=labels[i["id"]]["verdict"], justin_reason=labels[i["id"]].get("reason"),
            verdicts=verdicts[i["id"]], intake=i["intake"], output=i["output"],
        ) for i in items],
    )  # fmt: skip


@router.get("/explore/search")
def explore_search(q: str, request: Request, bike_id: str | None = None) -> list[SearchHit]:
    """What retrieval returns for a query: the ranked chunks with their scores. Search is
    local (the embedding model runs in the app), so exploring costs nothing."""
    query = q.strip()
    if not query or len(query) > 300:
        raise HTTPException(422, "Give a query of 1 to 300 characters.")
    deps = request.app.state.cw.deps
    with deps.connect() as conn:
        return search_knowledge(conn, query, bike_id=bike_id or None, k=8, embedder=deps.embedder,
                                mode=SearchMode.VECTOR)  # fmt: skip


class PartOption(BaseModel):
    part_id: str
    category: str
    name: str


class CompatView(BaseModel):
    bike_id: str
    bike_name: str
    part_id: str
    part_name: str
    category: str
    bike_specs: dict[str, Any]
    part_specs: dict[str, Any]
    results: list[CompatResult]  # one per wheel for tires, tubes and rotors


@router.get("/explore/parts")
def explore_parts(request: Request) -> list[PartOption]:
    with request.app.state.cw.deps.connect() as conn:
        rows = conn.execute(
            "SELECT id, category, brand || ' ' || name FROM parts ORDER BY category, id"
        ).fetchall()
    return [PartOption(part_id=r[0], category=r[1], name=r[2]) for r in rows]


@router.get("/explore/compat")
def explore_compat(
    bike_id: str, part_id: str, request: Request, tire_width_mm: int | None = None
) -> CompatView:
    """The compatibility engine's verdict, with the reasons and the specs it compared. This is
    the code the agent can't override: the model never decides whether a part fits."""
    with request.app.state.cw.deps.connect() as conn:
        bike, part = load_bike(conn, bike_id), load_part(conn, part_id)
        if bike is None:
            raise HTTPException(404, f"no bike {bike_id}")
        if part is None:
            raise HTTPException(404, f"no part {part_id}")
        results = check_all_positions(bike, part, load_rules(conn), tire_width_mm)
    return CompatView(
        bike_id=bike_id, bike_name=bike_name(bike), part_id=part_id,
        part_name=f"{part.brand} {part.name}",
        category=PartCategory(part.category).value,
        bike_specs=bike.model_dump(mode="json"), part_specs=part.specs.model_dump(mode="json"),
        results=results,
    )  # fmt: skip


class LiveScore(BaseModel):
    key: str
    score: float | None
    comment: str | None


class RunScores(BaseModel):
    stage: str  # "triage" or "drafting"
    run_id: str
    scores: list[LiveScore]


class OrderScores(BaseModel):
    available: bool
    reason: str | None = None
    runs: list[RunScores] = []


@router.get("/orders/{order_id}/scores")
def order_scores(order_id: int, request: Request) -> OrderScores:
    """Every score LangSmith holds for the order's triage and drafting runs: the live checks,
    the judges, the mechanic's decision and the thumbs. Reads LangSmith, so only when tracing
    is on; otherwise it says so rather than failing."""
    from counterwrench.api.app import live_scoring_enabled

    with request.app.state.cw.deps.connect() as conn:
        row = conn.execute(
            "SELECT langsmith_run_id, draft_run_id FROM work_orders WHERE id = %s", (order_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(404, f"no work order {order_id}")
    if not live_scoring_enabled():
        return OrderScores(available=False, reason="Tracing is off in this deployment.")
    runs = [(stage, str(rid)) for stage, rid in (("triage", row[0]), ("drafting", row[1])) if rid]
    try:
        from langsmith import Client

        client = Client()
        found = [
            RunScores(stage=stage, run_id=rid, scores=sorted(
                (LiveScore(key=f.key, score=f.score, comment=f.comment)
                 for f in client.list_feedback(run_ids=[rid])), key=lambda s: s.key))
            for stage, rid in runs
        ]  # fmt: skip
    except Exception as exc:  # LangSmith being slow or down must not break the order page
        log.warning("couldn't read live scores for order %s: %s", order_id, exc)
        return OrderScores(available=False, reason="LangSmith couldn't be reached.")
    return OrderScores(available=True, runs=found)
