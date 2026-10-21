"""The production report and the harvest file: the arithmetic, the ordering, the guardrails."""

from counterwrench.online.harvest import harvest
from counterwrench.online.ratings import Vote
from counterwrench.online.report import render, summarize


def order(oid, status="approved", severity="needs_service", edited_by=None, notes=None, **intake):
    return {"id": oid, "status": status, "severity": severity, "edited_by": edited_by,
            "review_notes": notes, "intake": intake, "customer_explanation": "x",
            "mechanic_notes": None, "draft_run_id": None, "langsmith_run_id": None}  # fmt: skip


ORDERS = [
    order(1),
    order(2, edited_by="sam"),
    order(3, "rejected", notes="wrong cassette"),
    order(4, "rejected", "safety_critical", notes="missed the crack", question_rounds={"r1": 2}),
    order(5, "awaiting_review", bike_unconfirmed=True),
]
VOTES = {1: [Vote("alex", "up", None)], 2: [Vote("alex", "down", "price is off")]}


def test_rates_count_only_orders_a_mechanic_has_decided():
    s = summarize(ORDERS, VOTES)
    assert (s.total, s.reviewed, s.approved_as_drafted, s.edited) == (5, 4, 1, 1)
    assert s.by_status["rejected"] == 2 and s.safety_critical == 1
    assert (s.question_limit, s.bike_unconfirmed, s.up, s.down) == (1, 1, 1, 1)


def test_problems_list_safety_first():
    ids = [p["id"] for p in summarize(ORDERS, VOTES).problems]
    assert ids == [4, 2, 3]  # the missed crack first, then by order


def test_the_report_renders_without_langsmith_and_with_nothing():
    text = render(summarize(ORDERS, VOTES))
    assert "Approved as drafted: 1/4 (25%)" in text and "#4 SAFETY" in text
    assert "Not available" in text
    assert "n/a" in render(summarize([], {})) and "None." in render(summarize([], {}))


def test_harvest_picks_rejected_edited_and_rated_orders_unlabeled():
    items = harvest(ORDERS, VOTES, {3: [{"item": "CHAIN", "qty": 1}]})
    assert [i["order_id"] for i in items] == [4, 1, 2, 3]  # safety first; order 5 untouched
    assert all(i["label"] is None for i in items)  # labels are Justin's
    assert items[3]["agent_output"]["lines"] == [{"item": "CHAIN", "qty": 1}]
    assert "thumbs-up from alex" in items[1]["picked_because"]
