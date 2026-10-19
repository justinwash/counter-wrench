import re

import pytest

from counterwrench.db.seed import load_seed
from counterwrench.rag.docs import DocError, anchor, load_docs, parse_doc

DOCS = load_docs()
SEED = load_seed()
LABOR_CODES = {item.code for item in SEED.labor_menu}
BIKE_IDS = {bike.id for bike in SEED.bikes}

# Backticked tokens shaped like labor codes, e.g. `HANGER-ALIGN`.
CODE_IN_TEXT = re.compile(r"`([A-Z0-9]+(?:-[A-Z0-9]+)+)`")


def test_knowledge_base_loads():
    assert DOCS


@pytest.mark.parametrize("doc", DOCS, ids=lambda d: d.doc_id)
def test_labor_codes_mentioned_exist(doc):
    text = "\n".join(s.body for s in doc.sections) + doc.intro
    assert set(CODE_IN_TEXT.findall(text)) <= LABOR_CODES


@pytest.mark.parametrize("doc", DOCS, ids=lambda d: d.doc_id)
def test_bike_ids_exist(doc):
    assert set(doc.meta.bike_ids) <= BIKE_IDS


def test_chunk_ids_are_unique():
    ids = [f"{d.doc_id}#{s.anchor}" for d in DOCS for s in d.sections]
    assert len(ids) == len(set(ids))


# --- Parser --------------------------------------------------------------------------------------

GOOD = """---
title: Example
doc_type: diagnosis
complaints: [creak]
---

Intro text.

## First section

Body one. <!-- VERIFY: review note -->

## Second section

Body two.
"""


def test_parses_sections_and_strips_review_notes():
    doc = parse_doc("example", GOOD)
    assert [s.anchor for s in doc.sections] == ["first-section", "second-section"]
    assert "VERIFY" not in doc.sections[0].body
    assert doc.intro == "Intro text."


def test_windows_line_endings_parse_the_same():
    assert parse_doc("x", GOOD.replace("\n", "\r\n")).sections == parse_doc("x", GOOD).sections


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("## No frontmatter\n\nBody.", "frontmatter"),
        (GOOD.replace("doc_type: diagnosis", "doc_type: rumor"), "doc_type"),
        (GOOD.replace("complaints: [creak]", "complaints: [explodes]"), "complaints"),
        (GOOD.replace("Body two.", ""), "empty"),
        (GOOD.replace("## Second section", "## First section"), "share a heading"),
        (GOOD.split("## First")[0], "at least one"),
    ],
)
def test_parser_rejects_bad_docs(text, message):
    with pytest.raises(DocError, match=message):
        parse_doc("bad", text)


def test_anchor():
    assert anchor("Soft lever: air vs. worn pads") == "soft-lever-air-vs-worn-pads"


# --- Coverage ----------------------------------------------------------------------------------


def test_every_complaint_has_a_diagnosis_guide():
    # `other` is free text by definition; every specific complaint needs a guide to retrieve.
    from counterwrench.rag.docs import DocType
    from counterwrench.taxonomy import Complaint

    covered = {c for d in DOCS if d.meta.doc_type is DocType.DIAGNOSIS for c in d.meta.complaints}
    missing = set(Complaint) - {Complaint.OTHER} - covered
    assert not missing, f"no diagnosis guide covers: {sorted(missing)}"
