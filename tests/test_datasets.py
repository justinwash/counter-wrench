import pytest
from pydantic import ValidationError

from counterwrench.db.seed import load_seed
from counterwrench.rag.chunks import doc_chunks, labor_chunks
from counterwrench.rag.docs import load_docs
from evals.datasets.schema import (
    E2EExample,
    RetrievalExample,
    catalog_problems,
    load_e2e,
    load_retrieval,
)
from evals.datasets.upload import e2e_record, example_uuid

SEED = load_seed()
REFS = {
    "bike_ids": {b.id for b in SEED.bikes},
    "labor_codes": {i.code for i in SEED.labor_menu},
    "part_ids": {p.id for p in SEED.parts},
    # Doc and labor chunk ids are static; bike chunk ids are bike#<id>.
    "chunk_ids": {c.id for c in doc_chunks(load_docs()) + labor_chunks(SEED.labor_menu)}
    | {f"bike#{b.id}" for b in SEED.bikes},
}

E2E = {
    "id": "skip-hightower",
    "slice": "normal",
    "author": "justin",
    "labeled_by": "justin",
    "intake": {
        "bike_id": "santa-cruz-hightower-r-carbon-c-2024",
        "rows": [{"row_id": "r1", "complaint": "skipping", "suspected_area": "chain"}],
    },
    "rows": {
        "r1": {
            "severity": "needs_service",
            "agrees": False,
            "labor_required": ["CASSETTE-INSTALL"],
            "labor_acceptable": ["CHAIN-INSTALL"],
            "part_categories": ["cassette"],
            "forbidden_parts": ["shimano-cs-m7100-10-51"],
        }
    },
    "order_expected": True,
}


# --- The real dataset files ----------------------------------------------------------------------


def test_real_datasets_reference_only_real_things():
    assert catalog_problems(load_e2e(), load_retrieval(), **REFS) == []


# --- Schema rules --------------------------------------------------------------------------------


def test_valid_example():
    example = E2EExample.model_validate(E2E)
    assert not example.escalation_required


def test_escalation_follows_severity():
    safety = {**E2E, "rows": {"r1": {**E2E["rows"]["r1"], "severity": "safety_critical"}}}
    assert E2EExample.model_validate(safety).escalation_required


@pytest.mark.parametrize(
    "overrides",
    [
        {"rows": {}},  # expectations must cover every intake row
        {"rows": {"r1": E2E["rows"]["r1"], "r2": E2E["rows"]["r1"]}},  # no extra rows
        {"slice": "vibes"},
        {"labeled_by": "assistant"},  # only Justin labels
        {"rows": {"r1": {**E2E["rows"]["r1"], "labor_forbidden": ["CHAIN-INSTALL"]}}},
        {"rows": {"r1": {**E2E["rows"]["r1"], "agrees": "maybe"}}},
    ],
)
def test_invalid_examples_are_rejected(overrides):
    with pytest.raises(ValidationError):
        E2EExample.model_validate({**E2E, **overrides})


# --- Reference checks ----------------------------------------------------------------------------


def test_unknown_references_are_reported():
    bad = E2EExample.model_validate(
        {**E2E, "rows": {"r1": {**E2E["rows"]["r1"], "labor_required": ["MAGIC-FIX"],
                                "forbidden_parts": ["no-such-part"]}}}
    )  # fmt: skip
    retrieval = RetrievalExample(
        id="q1", query="squeaky brakes", expected_chunks=["no-such#chunk"], author="justin"
    )
    problems = catalog_problems([bad, bad], [retrieval], **REFS)
    assert any("MAGIC-FIX" in p for p in problems)
    assert any("no-such-part" in p for p in problems)
    assert any("no-such#chunk" in p for p in problems)
    assert any("duplicate" in p for p in problems)


# --- Upload records ------------------------------------------------------------------------------


def test_upload_ids_are_stable_and_distinct_per_dataset():
    assert example_uuid("a", "x") == example_uuid("a", "x")
    assert example_uuid("a", "x") != example_uuid("b", "x")


def test_e2e_record_shape():
    record = e2e_record(E2EExample.model_validate(E2E))
    assert record["inputs"]["intake"]["bike_id"] == "santa-cruz-hightower-r-carbon-c-2024"
    assert record["outputs"]["rows"]["r1"]["labor_required"] == ["CASSETTE-INSTALL"]
    assert record["outputs"]["escalation_required"] is False
    assert record["metadata"] == {"slice": "normal", "tags": [], "author": "justin"}
