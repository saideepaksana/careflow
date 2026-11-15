from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from careflow.agents.careplan import CarePlanResult
from careflow.config import EVAL_TOP_K

RAG_GOLDEN_PATH = Path(__file__).with_name("data") / "rag_golden.jsonl"
SUPERSEDED = "superseded"

QuestionKind = Literal[
    "patient", "protocol", "operations", "stale_trap", "condition_trap", "not_covered"
]


class RagCase(BaseModel):
    id: str
    patient_id: str
    question: str
    relevant: list[str]
    kind: QuestionKind


class RetrievalScores(BaseModel):
    questions: int
    recall_at_5: float
    mrr: float
    stale_hit_rate: float
    missed: list[str]


class AnswerScores(BaseModel):
    covered: int
    not_covered: int
    failed: int
    answered_rate: float
    handoff_rate: float
    relevant_citation_rate: float
    unanswered: list[str]
    answered_not_covered: list[str]


def load_rag_cases(path: Path = RAG_GOLDEN_PATH) -> list[RagCase]:
    return [RagCase.model_validate_json(line) for line in path.read_text().splitlines() if line]


def recall_at_k(ranked: list[str], relevant: list[str], k: int) -> float:
    return len(set(ranked[:k]) & set(relevant)) / len(relevant)


def reciprocal_rank(ranked: list[str], relevant: list[str]) -> float:
    ranks = [rank for rank, chunk_id in enumerate(ranked, start=1) if chunk_id in relevant]
    return 1 / ranks[0] if ranks else 0.0


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def score_retrieval(
    cases: list[RagCase], rankings: list[list[str]], statuses: dict[str, str]
) -> RetrievalScores:
    covered = [
        (case, ranked) for case, ranked in zip(cases, rankings, strict=True) if case.relevant
    ]
    stale = [
        any(statuses.get(chunk_id) == SUPERSEDED for chunk_id in ranked[:EVAL_TOP_K])
        for ranked in rankings
    ]
    return RetrievalScores(
        questions=len(covered),
        recall_at_5=mean(
            [recall_at_k(ranked, case.relevant, EVAL_TOP_K) for case, ranked in covered]
        ),
        mrr=mean([reciprocal_rank(ranked, case.relevant) for case, ranked in covered]),
        stale_hit_rate=mean([float(hit) for hit in stale]),
        missed=[
            case.id for case, ranked in covered if not set(ranked[:EVAL_TOP_K]) & set(case.relevant)
        ],
    )


def score_answers(cases: list[RagCase], results: list[CarePlanResult | None]) -> AnswerScores:
    pairs = [(case, result) for case, result in zip(cases, results, strict=True) if result]
    covered = [(case, result) for case, result in pairs if case.relevant]
    not_covered = [(case, result) for case, result in pairs if not case.relevant]
    answered = [(case, result) for case, result in covered if not result.handed_off]
    return AnswerScores(
        covered=len(covered),
        not_covered=len(not_covered),
        failed=len(cases) - len(pairs),
        answered_rate=len(answered) / len(covered) if covered else 0.0,
        handoff_rate=mean([float(result.handed_off) for _, result in not_covered]),
        relevant_citation_rate=mean(
            [
                float(bool(set(result.cited_chunk_ids) & set(case.relevant)))
                for case, result in answered
            ]
        ),
        unanswered=[case.id for case, result in covered if result.handed_off],
        answered_not_covered=[case.id for case, result in not_covered if not result.handed_off],
    )
