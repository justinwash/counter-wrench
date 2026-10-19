"""The agent's tools: thin LangChain wrappers over tested deterministic code.

Each tool opens its own database connection (via ToolContext) and returns JSON the model reads.
Errors come back as text in the result, not exceptions: an agent can recover from an
informative message, while a crash just ends the run.
"""

from __future__ import annotations

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field

from counterwrench.rag.search import search_knowledge as _search
from counterwrench.tools import bikes, labor, parts, work_orders
from counterwrench.tools.context import ToolContext


class LookupBikeArgs(BaseModel):
    description: str = Field(
        description="The bike as the customer described it, e.g. '2023 Marlin 7'."
    )


class SearchKnowledgeArgs(BaseModel):
    query: str = Field(
        description="What to look up, in plain words. Include the bike, the symptom and the "
        "customer's own description (the intake note), not just the complaint category."
    )
    bike_id: str | None = Field(
        default=None, description="Catalog bike id, to include that bike's spec sheet."
    )


class FindPartsArgs(BaseModel):
    bike_id: str = Field(description="Catalog bike id (from the intake form or lookup_bike).")
    category: str = Field(
        description="One of: cassette, chain, rear_derailleur, brake_pads, rotor, "
        "bottom_bracket, tire, tube."
    )
    tire_width_mm: int | None = Field(
        default=None, description="Installed tire width in mm; needed to size tubes."
    )


class LaborCodeArgs(BaseModel):
    code: str = Field(description="A service menu code, e.g. 'BRAKE-BLEED'.")


class LaborSearchArgs(BaseModel):
    query: str = Field(description="The job in plain words, e.g. 'bleed hydraulic brake'.")


def make_tools(ctx: ToolContext | None = None) -> list[BaseTool]:
    ctx = ctx or ToolContext()

    def lookup_bike(description: str) -> str:
        with ctx.connect() as conn:
            return bikes.lookup_bike(conn, description).model_dump_json(exclude_none=True)

    def search_knowledge(query: str, bike_id: str | None = None) -> str:
        with ctx.connect() as conn:
            hits = _search(conn, query, bike_id=bike_id, embedder=ctx.embedder)
        return "[" + ",".join(h.model_dump_json(exclude={"score"}) for h in hits) + "]"

    def find_compatible_parts(bike_id: str, category: str, tire_width_mm: int | None = None) -> str:
        with ctx.connect() as conn:
            result = parts.find_compatible_parts(conn, bike_id, category, tire_width_mm)
        return result.model_dump_json(exclude_none=True)

    def get_labor_item(code: str) -> str:
        with ctx.connect() as conn:
            return labor.get_labor_item(conn, code).model_dump_json(exclude_none=True)

    def search_labor_menu(query: str) -> str:
        with ctx.connect() as conn:
            return labor.search_labor_menu(conn, query).model_dump_json(exclude_none=True)

    def draft_work_order(**kwargs) -> str:
        args = work_orders.DraftWorkOrderArgs.model_validate(kwargs)
        with ctx.connect() as conn:
            result = work_orders.draft_work_order(conn, args)
        return result.model_dump_json(exclude_none=True)

    return [
        StructuredTool.from_function(
            lookup_bike, args_schema=LookupBikeArgs,
            description="Resolve a free-text bike description to a catalog bike. Returns "
            "found (with specs), ambiguous (ask the customer which one), or not_found.",
        ),
        StructuredTool.from_function(
            search_knowledge, args_schema=SearchKnowledgeArgs,
            description="Search the shop's knowledge base (diagnosis guides, standards, "
            "policies, service menu, bike spec sheets). Cite the chunk_id of what you use.",
        ),
        StructuredTool.from_function(
            find_compatible_parts, args_schema=FindPartsArgs,
            description="List parts in a category that fit the bike, checked by the "
            "compatibility engine. Only suggest parts from 'compatible'; anything in "
            "'unverified' must be marked unverified for a mechanic to confirm.",
        ),
        StructuredTool.from_function(
            get_labor_item, args_schema=LaborCodeArgs,
            description="Look up one service menu item by its exact code.",
        ),
        StructuredTool.from_function(
            search_labor_menu, args_schema=LaborSearchArgs,
            description="Find service menu items by describing the job. Use the codes it "
            "returns; never invent codes.",
        ),
        StructuredTool.from_function(
            draft_work_order, name="draft_work_order",
            args_schema=work_orders.DraftWorkOrderArgs,
            description="Save the draft work order for mechanic review. Give labor codes, "
            "part ids and quantities only: prices and the total come from the catalog. Every "
            "part is re-checked; a rejected draft saves nothing and lists what to fix.",
        ),
    ]  # fmt: skip
