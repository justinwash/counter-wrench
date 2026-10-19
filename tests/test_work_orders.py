import json
from contextlib import nullcontext

import pytest
from psycopg import errors

from counterwrench.db.migrate import migrate
from counterwrench.db.seed import load_seed, sync
from counterwrench.tools import make_tools
from counterwrench.tools.context import ToolContext
from counterwrench.tools.work_orders import DraftWorkOrderArgs, draft_work_order

HIGHTOWER = "santa-cruz-hightower-r-carbon-c-2024"
STUMPJUMPER = "specialized-stumpjumper-15-comp-alloy-2025"
SLASH = "trek-slash-9-8-xt-gen-6-2024"


@pytest.fixture
def db(conn):
    migrate(conn)
    sync(conn, load_seed())
    return conn


def args(**overrides):
    base = {
        "bike_id": HIGHTOWER,
        "severity": "needs_service",
        "labor_lines": [{"code": "CASSETTE-INSTALL"}],
        "part_lines": [{"part_id": "sram-pg-1230-11-50"}],
        "customer_explanation": "Your cassette is worn; a new one stops the skipping.",
    }
    return DraftWorkOrderArgs.model_validate({**base, **overrides})


def count(conn, table):
    return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


# --- Saved drafts ------------------------------------------------------------------------------


def test_valid_draft_is_saved_awaiting_review_with_catalog_prices(db):
    result = draft_work_order(db, args())
    assert result.status == "saved"
    order = db.execute(
        "SELECT status, estimate_total_cents, priority FROM work_orders WHERE id = %s",
        (result.work_order_id,),
    ).fetchone()
    # CASSETTE-INSTALL $15 + PG-1230 $75, both from the catalog.
    assert order == ("awaiting_review", 9000, False)
    assert result.estimate_total == "$90.00"


def test_model_cannot_supply_prices(db):
    # The schema has no price field; anything extra is ignored and the catalog wins.
    raw = args().model_dump(mode="json")
    raw["labor_lines"][0]["unit_price_cents"] = 1
    raw["estimate_total_cents"] = 1
    result = draft_work_order(db, DraftWorkOrderArgs.model_validate(raw))
    assert result.estimate_total == "$90.00"


def test_quantities_multiply_catalog_prices(db):
    result = draft_work_order(
        db, args(labor_lines=[{"code": "BRAKE-BLEED", "qty": 2}], part_lines=[])
    )
    assert result.estimate_total == "$80.00"


def test_safety_critical_drafts_are_priority(db):
    result = draft_work_order(db, args(severity="safety_critical"))
    priority = db.execute(
        "SELECT priority FROM work_orders WHERE id = %s", (result.work_order_id,)
    ).fetchone()
    assert priority == (True,)


def test_unknown_fit_is_saved_flagged_with_its_reason(db):
    # No max tire width on file for the Stumpjumper: the engine can't confirm the fit.
    result = draft_work_order(
        db,
        args(
            bike_id=STUMPJUMPER,
            labor_lines=[{"code": "TIRE-INSTALL"}],
            part_lines=[{"part_id": "maxxis-dhf-29x2-5", "position": "front"}],
        ),
    )
    assert result.status == "saved" and result.unverified_parts == ["maxxis-dhf-29x2-5"]
    line = db.execute(
        "SELECT unverified, unverified_reason FROM work_order_lines WHERE part_id IS NOT NULL"
    ).fetchone()
    assert line[0] is True and "max tire width" in line[1]


def test_freetext_bike_can_get_labor_but_no_parts(db):
    ok = draft_work_order(db, args(bike_id=None, bike_freetext="old blue Huffy", part_lines=[]))
    assert ok.status == "saved"
    refused = draft_work_order(db, args(bike_id=None, bike_freetext="old blue Huffy"))
    assert refused.status == "rejected" and "catalog bike" in refused.problems[0]


# --- Rejected drafts write nothing ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "problem"),
    [
        ({"part_lines": [{"part_id": "shimano-cs-m7100-10-51"}]}, "doesn't fit"),
        ({"labor_lines": [{"code": "MAGIC-FIX"}]}, "Unknown labor code"),
        ({"part_lines": [{"part_id": "no-such-part"}]}, "Unknown part"),
        ({"bike_id": "no-such-bike"}, "lookup_bike"),
        ({"bike_id": SLASH, "part_lines": [{"part_id": "maxxis-dhr2-29x2-4"}]}, "which wheel"),
        (
            {
                "bike_id": SLASH,
                "part_lines": [{"part_id": "maxxis-dhr2-29x2-4", "position": "rear"}],
            },
            "doesn't fit",  # mullet: the 29" tire only fits the front
        ),
        ({"bike_id": None}, "bike_id"),
    ],
)
def test_any_problem_rejects_the_whole_draft(db, overrides, problem):
    result = draft_work_order(db, args(**overrides))
    assert result.status == "rejected"
    assert any(problem in p for p in result.problems)
    assert count(db, "work_orders") == 0 and count(db, "work_order_lines") == 0


def test_all_problems_reported_at_once(db):
    result = draft_work_order(
        db,
        args(
            labor_lines=[{"code": "MAGIC-FIX"}],
            part_lines=[{"part_id": "shimano-cs-m7100-10-51"}],
        ),
    )
    assert len(result.problems) == 2


# --- Database guarantees -----------------------------------------------------------------------


def test_database_refuses_approval_without_a_review_record(db):
    order_id = draft_work_order(db, args()).work_order_id
    with pytest.raises(errors.CheckViolation):
        db.execute("UPDATE work_orders SET status = 'approved' WHERE id = %s", (order_id,))
    db.execute(
        "UPDATE work_orders SET status = 'approved', reviewed_by = 'justin', "
        "reviewed_at = now() WHERE id = %s",
        (order_id,),
    )


def test_seed_cannot_delete_a_part_an_order_uses(db):
    draft_work_order(db, args())
    data = load_seed()
    data.parts = [p for p in data.parts if p.id != "sram-pg-1230-11-50"]
    with pytest.raises(errors.ForeignKeyViolation):
        sync(db, data)
    assert db.execute("SELECT 1 FROM parts WHERE id = 'sram-pg-1230-11-50'").fetchone()


def test_later_price_change_does_not_rewrite_old_estimates(db):
    draft_work_order(db, args())
    db.execute("UPDATE parts SET price_cents = 99999 WHERE id = 'sram-pg-1230-11-50'")
    line_price = db.execute(
        "SELECT unit_price_cents FROM work_order_lines WHERE part_id = 'sram-pg-1230-11-50'"
    ).fetchone()
    assert line_price == (7500,)


# --- As a tool ---------------------------------------------------------------------------------


def test_tool_saves_and_reports(db):
    tools = {t.name: t for t in make_tools(ToolContext(connect=lambda: nullcontext(db)))}
    out = json.loads(tools["draft_work_order"].invoke(args().model_dump(mode="json")))
    assert out["status"] == "saved" and out["work_order_status"] == "awaiting_review"
