"""Load the knowledge base (data/docs/*.md): YAML frontmatter plus `##` sections.

Each `##` section is written to stand alone and becomes one retrieval chunk, identified as
`<doc_id>#<anchor>`. Headings are kept stable so eval datasets can point at them. HTML comments
(`<!-- ... -->`) are review notes and are stripped, so they never reach the agent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import Field, ValidationError

from counterwrench.models import ShortText, Slug, Strict
from counterwrench.taxonomy import Complaint

DOCS_DIR = Path(__file__).resolve().parents[3] / "data" / "docs"

_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


class DocType(StrEnum):
    POLICY = "policy"  # what the shop does and won't do
    STANDARDS = "standards"  # how bike standards work and fit together
    DIAGNOSIS = "diagnosis"  # symptoms -> likely causes -> what we check
    NORMAL = "normal"  # things that look wrong but are working as intended


class DocMeta(Strict):
    title: ShortText
    doc_type: DocType
    # Complaints this doc helps diagnose; drives the taxonomy coverage test.
    complaints: list[Complaint] = Field(default_factory=list)
    # Catalog bikes the doc is specifically about (empty = applies generally).
    bike_ids: list[Slug] = Field(default_factory=list)


@dataclass(frozen=True)
class Section:
    heading: str
    anchor: str
    body: str


@dataclass(frozen=True)
class Doc:
    doc_id: str
    meta: DocMeta
    intro: str
    sections: list[Section]


class DocError(Exception):
    pass


def anchor(heading: str) -> str:
    """'Soft lever: air vs. worn pads' -> 'soft-lever-air-vs-worn-pads'."""
    return re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")


def parse_doc(doc_id: str, text: str) -> Doc:
    text = text.replace("\r\n", "\n")
    match = _FRONTMATTER.match(text)
    if not match:
        raise DocError(f"{doc_id}: missing YAML frontmatter between --- lines")
    try:
        meta = DocMeta.model_validate(yaml.safe_load(match.group(1)) or {})
    except ValidationError as exc:
        raise DocError(f"{doc_id}: invalid frontmatter:\n{exc}") from exc

    body = _COMMENT.sub("", text[match.end() :])
    parts = re.split(r"^## (.+)$", body, flags=re.MULTILINE)
    intro, sections = parts[0].strip(), []
    for heading, content in zip(parts[1::2], parts[2::2], strict=True):
        content = content.strip()
        if not content:
            raise DocError(f"{doc_id}: section '{heading}' is empty")
        sections.append(Section(heading.strip(), anchor(heading), content))
    if not sections:
        raise DocError(f"{doc_id}: needs at least one '## ' section")
    anchors = [s.anchor for s in sections]
    if len(anchors) != len(set(anchors)):
        raise DocError(f"{doc_id}: two sections share a heading")
    return Doc(doc_id, meta, intro, sections)


def load_docs(directory: Path = DOCS_DIR) -> list[Doc]:
    return [
        parse_doc(path.stem, path.read_text("utf-8")) for path in sorted(directory.glob("*.md"))
    ]
