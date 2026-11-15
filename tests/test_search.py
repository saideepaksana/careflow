import psycopg
import pytest

from careflow.config import CONTEXT_CHUNKS, CORPUS_DIR
from careflow.db import repository
from careflow.knowledge.corpus import ingest_corpus
from careflow.knowledge.rerank import FakeReranker
from careflow.knowledge.search import RetrievalMode, rank_chunks, retrieve, rrf_fuse
from careflow.memory.embeddings import FakeEmbedder

EMBEDDER = FakeEmbedder()
RERANKER = FakeReranker()
FAQS = {"faq-lab-preparation", "faq-visits"}


@pytest.fixture
def corpus(db: psycopg.Connection) -> psycopg.Connection:
    ingest_corpus(db, EMBEDDER, CORPUS_DIR)
    return db


def visible_documents(conn: psycopg.Connection, patient_id: str) -> set[str]:
    embedding = EMBEDDER.embed(["anything"])[0]
    chunk_ids = repository.dense_search(conn, patient_id, embedding, 1000)
    return {chunk_id.split("#")[0] for chunk_id in chunk_ids}


def test_rrf_fuse_rewards_agreement() -> None:
    assert rrf_fuse([["a", "b"], ["b", "c"]]) == ["b", "a", "c"]


@pytest.mark.parametrize(
    ("patient_id", "documents"),
    [
        ("P001", {"P001-summary-v1", "P001-plan-v2", "protocol-heart-failure"}),
        ("P002", {"P002-summary-v1", "P002-plan-v1", "protocol-copd"}),
        ("P004", {"P004-summary-v1", "P004-plan-v1", "protocol-hip-replacement"}),
    ],
)
def test_only_own_current_and_matching_shared_documents_are_visible(
    corpus: psycopg.Connection, patient_id: str, documents: set[str]
) -> None:
    assert visible_documents(corpus, patient_id) == documents | FAQS


@pytest.mark.parametrize("mode", list(RetrievalMode))
def test_superseded_plan_is_never_ranked(corpus: psycopg.Connection, mode: RetrievalMode) -> None:
    query = "Limit fluids to 2 litres a day. Do not drive for 4 weeks."
    ranked = rank_chunks(corpus, EMBEDDER, RERANKER, "P001", query, mode)
    assert ranked
    assert not [chunk_id for chunk_id in ranked if chunk_id.startswith("P001-plan-v1")]


def test_keyword_search_finds_exact_drug_name(corpus: psycopg.Connection) -> None:
    assert "P003-plan-v1#medicines" in repository.keyword_search(corpus, "P003", "metformin", 5)


def test_keyword_search_matches_any_term(corpus: psycopg.Connection) -> None:
    ranked = repository.keyword_search(corpus, "P004", "staples zebra", 5)
    assert "P004-plan-v1#follow-up-visits" in ranked


def test_retrieve_returns_context_chunks(corpus: psycopg.Connection) -> None:
    chunks = retrieve(corpus, EMBEDDER, RERANKER, "P005", "How long will my cough last?")
    assert 0 < len(chunks) <= CONTEXT_CHUNKS
    assert all(chunk.title and chunk.heading for chunk in chunks)


def test_ingesting_twice_keeps_chunk_ids(corpus: psycopg.Connection) -> None:
    before = {row["id"] for row in corpus.execute("SELECT id FROM chunks").fetchall()}
    ingest_corpus(corpus, EMBEDDER, CORPUS_DIR)
    after = {row["id"] for row in corpus.execute("SELECT id FROM chunks").fetchall()}
    assert before == after
