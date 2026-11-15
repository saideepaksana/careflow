import json

from careflow.config import PROJECT_ROOT, load_settings
from careflow.db import repository
from careflow.db.connection import Connection, connect
from careflow.evaluation.rag_eval import RagCase, RetrievalScores, load_rag_cases, score_retrieval
from careflow.knowledge.rerank import FastReranker, Reranker
from careflow.knowledge.search import RetrievalMode, rank_chunks
from careflow.memory.embeddings import Embedder, FastEmbedder

REPORT_PATH = PROJECT_ROOT / "reports" / "retrieval_m4.json"


def evaluate_mode(
    conn: Connection,
    embedder: Embedder,
    reranker: Reranker,
    cases: list[RagCase],
    mode: RetrievalMode,
) -> RetrievalScores:
    rankings = [
        rank_chunks(conn, embedder, reranker, case.patient_id, case.question, mode)
        for case in cases
    ]
    statuses = repository.chunk_status(
        conn, [chunk_id for ranked in rankings for chunk_id in ranked]
    )
    return score_retrieval(cases, rankings, statuses)


def main() -> None:
    cases = load_rag_cases()
    embedder, reranker = FastEmbedder(), FastReranker()
    with connect(load_settings().database_url) as conn:
        report = {
            mode.value: evaluate_mode(conn, embedder, reranker, cases, mode).model_dump()
            for mode in RetrievalMode
        }
    print(f"{'mode':<15} {'recall@5':>9} {'mrr':>6} {'stale':>6}  missed")
    for mode, scores in report.items():
        print(
            f"{mode:<15} {scores['recall_at_5']:>9.3f} {scores['mrr']:>6.3f}"
            f" {scores['stale_hit_rate']:>6.3f}  {', '.join(scores['missed'])}"
        )
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n")
    print(f"report written to {REPORT_PATH.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
