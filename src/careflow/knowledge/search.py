from enum import StrEnum

from pydantic import BaseModel

from careflow.config import CONTEXT_CHUNKS, RECALL_CANDIDATES, RRF_K
from careflow.db import repository
from careflow.db.connection import Connection
from careflow.knowledge.rerank import Reranker
from careflow.memory.embeddings import Embedder


class RetrievalMode(StrEnum):
    DENSE = "dense"
    HYBRID = "hybrid"
    HYBRID_RERANK = "hybrid_rerank"


class RetrievedChunk(BaseModel):
    id: str
    title: str
    heading: str
    content: str


def rrf_fuse(rankings: list[list[str]]) -> list[str]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1 / (RRF_K + rank)
    return sorted(scores, key=lambda chunk_id: (-scores[chunk_id], chunk_id))


def rerank(conn: Connection, reranker: Reranker, query: str, chunk_ids: list[str]) -> list[str]:
    chunks = repository.get_chunks(conn, chunk_ids)
    if not chunks:
        return []
    texts = [f"{chunk['title']}: {chunk['heading']}\n{chunk['content']}" for chunk in chunks]
    scores = reranker.score(query, texts)
    ranked = sorted(zip(scores, chunks, strict=True), key=lambda pair: -pair[0])
    return [chunk["id"] for _, chunk in ranked]


def rank_chunks(
    conn: Connection,
    embedder: Embedder,
    reranker: Reranker,
    patient_id: str,
    query: str,
    mode: RetrievalMode,
) -> list[str]:
    embedding = embedder.embed([query])[0]
    dense = repository.dense_search(conn, patient_id, embedding, RECALL_CANDIDATES)
    if mode == RetrievalMode.DENSE:
        return dense
    keyword = repository.keyword_search(conn, patient_id, query, RECALL_CANDIDATES)
    fused = rrf_fuse([keyword, dense])[:RECALL_CANDIDATES]
    if mode == RetrievalMode.HYBRID:
        return fused
    return rerank(conn, reranker, query, fused)


def retrieve(
    conn: Connection, embedder: Embedder, reranker: Reranker, patient_id: str, query: str
) -> list[RetrievedChunk]:
    ranked = rank_chunks(conn, embedder, reranker, patient_id, query, RetrievalMode.HYBRID_RERANK)
    rows = repository.get_chunks(conn, ranked[:CONTEXT_CHUNKS])
    return [RetrievedChunk.model_validate(row) for row in rows]
