import dataclasses

import pytest

from counterwrench.catalog import BikeSpec
from counterwrench.db.migrate import migrate
from counterwrench.db.seed import load_seed
from counterwrench.rag.chunks import bike_chunks, doc_chunks, labor_chunks
from counterwrench.rag.docs import load_docs
from counterwrench.rag.embed import DIM, FakeEmbedder
from counterwrench.rag.ingest import ingest
from counterwrench.rag.search import SearchMode, rrf, search_knowledge

SEED = load_seed()
BIKES = [BikeSpec.model_validate(b.model_dump(exclude={"source"})) for b in SEED.bikes]
DOCS = load_docs()
CHUNKS = doc_chunks(DOCS) + labor_chunks(SEED.labor_menu) + bike_chunks(BIKES)
FUEL = "trek-fuel-ex-8-gen-6-2023"
SLASH = "trek-slash-9-8-xt-gen-6-2024"


class CountingEmbedder(FakeEmbedder):
    def __init__(self):
        self.embedded = 0

    def embed_documents(self, texts):
        self.embedded += len(texts)
        return super().embed_documents(texts)


# --- Chunk building (no database) -----------------------------------------------------------


def test_chunk_counts_and_unique_ids():
    sections = sum(len(d.sections) for d in DOCS)
    assert len(CHUNKS) == sections + len(SEED.labor_menu) + len(SEED.bikes)
    assert len({c.id for c in CHUNKS}) == len(CHUNKS)


def test_labor_chunk_states_code_and_price():
    bleed = next(c for c in CHUNKS if c.id == "labor#BRAKE-BLEED")
    assert "BRAKE-BLEED" in bleed.content and "$40.00" in bleed.content


def test_bike_chunk_names_both_wheel_conventions_and_is_bike_specific():
    slash = next(c for c in CHUNKS if c.id == f"bike#{SLASH}")
    assert '622 mm (700c / 29")' in slash.content and '584 mm (650b / 27.5")' in slash.content
    assert slash.bike_ids == (SLASH,)


def test_rim_brake_bike_chunk_has_no_rotors():
    caad = next(c for c in CHUNKS if c.id == "bike#cannondale-caad10-5-105-2014")
    assert "no rotors" in caad.content


def test_embedded_text_leads_with_title_and_heading():
    chunk = next(c for c in CHUNKS if c.id == "diagnosis-brakes#grinding-when-braking")
    assert chunk.text.startswith("Diagnosing brake rub, noise, soft levers and weak braking - ")


def test_fake_embedder_dimension():
    assert len(FakeEmbedder().embed_query("creak")) == DIM


# --- Reciprocal Rank Fusion ---------------------------------------------------------------


def test_rrf_rewards_agreement_between_rankings():
    fused = [chunk_id for chunk_id, _ in rrf([["a", "b", "c"], ["b", "d"]])]
    assert fused[0] == "b"  # ranked by both beats ranked first by one
    assert set(fused) == {"a", "b", "c", "d"}


def test_rrf_single_ranking_keeps_its_order():
    assert [c for c, _ in rrf([["x", "y", "z"]])] == ["x", "y", "z"]


# --- Ingestion and search (real database, fake embeddings) ----------------------------------


@pytest.fixture
def kb(conn):
    migrate(conn)
    ingest(conn, CHUNKS, FakeEmbedder())
    return conn


def test_ingest_loads_every_chunk(kb):
    assert kb.execute("SELECT count(*) FROM doc_chunks").fetchone() == (len(CHUNKS),)


def test_second_ingest_embeds_nothing(kb):
    embedder = CountingEmbedder()
    report = ingest(kb, CHUNKS, embedder)
    assert (embedder.embedded, report.unchanged) == (0, len(CHUNKS))


def test_changed_chunk_is_re_embedded_and_removed_chunk_deleted(kb):
    changed = [
        dataclasses.replace(CHUNKS[0], content=CHUNKS[0].content + " Updated."),
        *CHUNKS[1:-1],
    ]
    embedder = CountingEmbedder()
    report = ingest(kb, changed, embedder)
    assert (embedder.embedded, report.updated, report.removed) == (1, 1, 1)


def test_fts_finds_exact_tokens(kb):
    hits = search_knowledge(kb, "BB30", mode=SearchMode.FTS, embedder=FakeEmbedder())
    assert hits and "bottom-brackets" in hits[0].chunk_id


def test_bike_specific_chunks_only_for_that_bike(kb):
    hits = search_knowledge(
        kb, "bike spec sheet wheels", bike_id=FUEL, k=40, mode=SearchMode.HYBRID,
        embedder=FakeEmbedder(),
    )  # fmt: skip
    bike_hits = {h.chunk_id for h in hits if h.chunk_id.startswith("bike#")}
    assert bike_hits == {f"bike#{FUEL}"}


def test_no_bike_means_no_spec_sheets(kb):
    hits = search_knowledge(
        kb, "bike spec sheet wheels", k=40, mode=SearchMode.HYBRID, embedder=FakeEmbedder()
    )
    assert not any(h.chunk_id.startswith("bike#") for h in hits)


@pytest.mark.parametrize("mode", list(SearchMode))
def test_every_mode_returns_scored_hits(kb, mode):
    hits = search_knowledge(kb, "brake bleed", k=3, mode=mode, embedder=FakeEmbedder())
    assert 0 < len(hits) <= 3
    assert all(h.score > 0 for h in hits)


def test_query_with_no_searchable_words_returns_nothing_for_fts(kb):
    assert search_knowledge(kb, "the and of", mode=SearchMode.FTS, embedder=FakeEmbedder()) == []
