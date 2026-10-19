import json
from contextlib import nullcontext

import pytest

from counterwrench.db.migrate import migrate
from counterwrench.db.seed import load_seed, sync
from counterwrench.rag.embed import FakeEmbedder
from counterwrench.rag.ingest import build_chunks, ingest
from counterwrench.tools import make_tools
from counterwrench.tools.bikes import match_bikes
from counterwrench.tools.context import ToolContext
from counterwrench.tools.parts import UNVERIFIED_LABEL

HIGHTOWER = "santa-cruz-hightower-r-carbon-c-2024"
SLASH = "trek-slash-9-8-xt-gen-6-2024"
STUMPJUMPER = "specialized-stumpjumper-15-comp-alloy-2025"


@pytest.fixture
def tools(conn):
    """Every tool, as the agent sees them, over a fully seeded test database."""
    migrate(conn)
    sync(conn, load_seed())
    ingest(conn, build_chunks(conn), FakeEmbedder())
    ctx = ToolContext(connect=lambda: nullcontext(conn), embedder=FakeEmbedder())
    return {tool.name: tool for tool in make_tools(ctx)}


def call(tools, name, **args):
    return json.loads(tools[name].invoke(args))


def test_tool_names_match_the_plan(tools):
    assert set(tools) == {
        "lookup_bike", "search_knowledge", "find_compatible_parts",
        "get_labor_item", "search_labor_menu", "draft_work_order",
    }  # fmt: skip


# --- lookup_bike ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("description", "status", "expected"),
    [
        ("Marlin 7", "ambiguous", {"trek-marlin-7-gen-3-2023", "trek-marlin-7-gen-3-2025"}),
        ("2023 Marlin 7", "found", {"trek-marlin-7-gen-3-2023"}),
        ("blue trek marlin 7 from 2025 i think", "found", {"trek-marlin-7-gen-3-2025"}),
        ("Fuel EX 8", "ambiguous", {"trek-fuel-ex-8-2012", "trek-fuel-ex-8-gen-6-2023"}),
        ("stumpjumper", "found", {STUMPJUMPER}),
        ("Huffy cruiser", "not_found", set()),
        ("Trek", "not_found", set()),  # make alone is too vague
    ],
)
def test_lookup_bike(tools, description, status, expected):
    result = call(tools, "lookup_bike", description=description)
    assert result["status"] == status
    found = {result["bike"]["bike_id"]} if "bike" in result else set()
    assert found | {c["bike_id"] for c in result.get("candidates", [])} == expected


def test_found_bike_specs_name_both_wheel_conventions(tools):
    result = call(tools, "lookup_bike", description="Slash 9.8")
    assert '622 mm (700c / 29")' in result["bike"]["specs"]
    assert '584 mm (650b / 27.5")' in result["bike"]["specs"]


def test_ambiguity_tells_the_agent_to_ask():
    from counterwrench.catalog import BikeSpec

    bikes = [BikeSpec.model_validate(b.model_dump(exclude={"source"})) for b in load_seed().bikes]
    assert "Ask the customer" in match_bikes("Marlin 7", bikes).message


# --- find_compatible_parts ------------------------------------------------------------------------


def test_incompatible_parts_are_omitted_with_reasons(tools):
    result = call(tools, "find_compatible_parts", bike_id=HIGHTOWER, category="cassette")
    listed = {p["part_id"] for p in result["compatible"]}
    assert listed == {"sram-pg-1210-11-50", "sram-pg-1230-11-50"}
    assert "shimano-cs-m7100-10-51" not in json.dumps(result)  # the wrong part never appears
    assert result["omitted_incompatible"] > 0 and result["omitted_reasons"]


def test_per_wheel_parts_carry_their_position(tools):
    result = call(tools, "find_compatible_parts", bike_id=SLASH, category="tire")
    dhr_29 = [p for p in result["compatible"] if p["part_id"] == "maxxis-dhr2-29x2-4"]
    assert [p["position"] for p in dhr_29] == ["front"]  # mullet: 29" only fits the front


def test_unknown_fit_is_labeled_unverified(tools):
    # No max tire width on file for this bike, so no tire can be confirmed.
    result = call(tools, "find_compatible_parts", bike_id=STUMPJUMPER, category="tire")
    assert result["compatible"] == []
    assert result["unverified"] and result["unverified_note"] == UNVERIFIED_LABEL


def test_tubes_need_a_tire_width(tools):
    without = call(tools, "find_compatible_parts", bike_id=HIGHTOWER, category="tube")
    with_width = call(
        tools, "find_compatible_parts", bike_id=HIGHTOWER, category="tube", tire_width_mm=61
    )
    assert without["compatible"] == [] and without["unverified"]
    assert {p["part_id"] for p in with_width["compatible"]} == {"tube-29x2-1-2-6-presta"}


@pytest.mark.parametrize(
    ("args", "message"),
    [
        ({"bike_id": "no-such-bike", "category": "chain"}, "lookup_bike"),
        ({"bike_id": HIGHTOWER, "category": "frame"}, "Unknown category"),
    ],
)
def test_bad_input_returns_an_error_message(tools, args, message):
    assert message in call(tools, "find_compatible_parts", **args)["error"]


# --- labor and knowledge -----------------------------------------------------------------------


def test_get_labor_item(tools):
    assert call(tools, "get_labor_item", code="brake-bleed")["item"]["price"] == "$40.00"
    assert "never invent" in call(tools, "get_labor_item", code="BRAKE-MAGIC")["error"]


@pytest.mark.parametrize(
    ("query", "code"),
    [
        ("bleed hydraulic brake", "BRAKE-BLEED"),
        ("true a wheel", "WHEEL-TRUE"),
        ("dropper post", "DROPPER-SERVICE"),
        ("suspension sag", "SUSPENSION-SETUP"),
    ],
)
def test_search_labor_menu(tools, query, code):
    items = call(tools, "search_labor_menu", query=query)["items"]
    assert code in [i["code"] for i in items]


def test_search_labor_menu_no_match(tools):
    assert "No service menu items" in call(tools, "search_labor_menu", query="xyzzy")["note"]


def test_search_knowledge_returns_citable_chunks(tools):
    hits = json.loads(tools["search_knowledge"].invoke({"query": "brake bleed"}))
    assert hits and {"chunk_id", "title", "heading", "content"} <= hits[0].keys()
