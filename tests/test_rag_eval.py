import pytest

from careflow.agents.careplan import CarePlanResult
from careflow.evaluation.rag_eval import (
    RagCase,
    load_rag_cases,
    recall_at_k,
    reciprocal_rank,
    score_answers,
    score_retrieval,
)


def case(case_id: str, relevant: list[str]) -> RagCase:
    kind = "patient" if relevant else "not_covered"
    return RagCase(id=case_id, patient_id="P001", question="q", relevant=relevant, kind=kind)


def answered(chunk_ids: list[str]) -> CarePlanResult:
    return CarePlanResult(reply="r", handed_off=False, cited_chunk_ids=chunk_ids)


HANDED_OFF = CarePlanResult(reply="h", handed_off=True, handoff_reason="not_covered")


@pytest.mark.parametrize(
    ("ranked", "relevant", "k", "expected"),
    [
        (["a", "b", "c"], ["c"], 2, 0.0),
        (["a", "b", "c"], ["b", "c"], 3, 1.0),
        (["a", "b"], ["b", "x"], 5, 0.5),
    ],
)
def test_recall_at_k(ranked: list[str], relevant: list[str], k: int, expected: float) -> None:
    assert recall_at_k(ranked, relevant, k) == expected


@pytest.mark.parametrize(
    ("ranked", "relevant", "expected"),
    [(["a", "b", "c"], ["c"], 1 / 3), (["a"], ["a"], 1.0), (["a"], ["x"], 0.0)],
)
def test_reciprocal_rank(ranked: list[str], relevant: list[str], expected: float) -> None:
    assert reciprocal_rank(ranked, relevant) == expected


def test_score_retrieval_skips_uncovered_and_counts_stale_hits() -> None:
    cases = [case("c1", ["a"]), case("c2", ["b"]), case("c3", [])]
    rankings = [["a"], ["old", "x"], ["old"]]
    scores = score_retrieval(cases, rankings, {"old": "superseded", "a": "current"})
    assert (scores.questions, scores.recall_at_5, scores.mrr) == (2, 0.5, 0.5)
    assert scores.stale_hit_rate == pytest.approx(2 / 3)
    assert scores.missed == ["c2"]


def test_score_answers() -> None:
    cases = [
        case("c1", ["a"]),
        case("c2", ["b"]),
        case("c3", []),
        case("c4", []),
        case("c5", ["c"]),
    ]
    results = [answered(["a"]), HANDED_OFF, HANDED_OFF, answered(["z"]), None]
    scores = score_answers(cases, results)
    assert (scores.covered, scores.not_covered, scores.failed) == (2, 2, 1)
    assert (scores.answered_rate, scores.handoff_rate, scores.relevant_citation_rate) == (
        0.5,
        0.5,
        1.0,
    )
    assert (scores.unanswered, scores.answered_not_covered) == (["c2"], ["c4"])


def test_golden_set_loads_with_unique_ids() -> None:
    cases = load_rag_cases()
    assert len(cases) == 60
    assert len({c.id for c in cases}) == len(cases)
