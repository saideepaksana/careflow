import time

from careflow.agents.careplan import CarePlanResult, answer_question
from careflow.config import EVAL_CASE_INTERVAL_SECONDS, PROJECT_ROOT, load_settings
from careflow.db.connection import Connection, connect
from careflow.evaluation.rag_eval import RagCase, load_rag_cases, score_answers
from careflow.knowledge.rerank import FastReranker, Reranker
from careflow.knowledge.search import retrieve
from careflow.llm.gateway import LLM, build_llm
from careflow.memory.embeddings import Embedder, FastEmbedder

REPORT_PATH = PROJECT_ROOT / "reports" / "careplan_m4.json"


def run_case(
    llm: LLM, conn: Connection, embedder: Embedder, reranker: Reranker, case: RagCase
) -> CarePlanResult | None:
    time.sleep(EVAL_CASE_INTERVAL_SECONDS)
    chunks = retrieve(conn, embedder, reranker, case.patient_id, case.question)
    result = answer_question(llm, case.question, chunks)
    if result.handoff_reason == "llm_failed":
        print(f"{case.id}: failed")
        return None
    print(f"{case.id}: {result.handoff_reason or ', '.join(result.cited_chunk_ids)}")
    return result


def main() -> None:
    llm = build_llm(load_settings())
    embedder, reranker = FastEmbedder(), FastReranker()
    cases = load_rag_cases()
    with connect(load_settings().database_url) as conn:
        results = [run_case(llm, conn, embedder, reranker, case) for case in cases]
    scores = score_answers(cases, results)
    for name, value in scores.model_dump().items():
        print(f"{name:<24} {value}")
    REPORT_PATH.write_text(scores.model_dump_json(indent=2) + "\n")
    print(f"report written to {REPORT_PATH.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
