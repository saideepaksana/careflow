from careflow.agents.intake import Turn
from careflow.evaluation.memory_eval import (
    MemoryCase,
    SemanticFactLabel,
    SummaryFactLabel,
    load_memory_cases,
    score_memory,
)
from careflow.memory.manager import SemanticFact, SemanticKey, SessionDigest
from careflow.memory.working import SessionSummary

CASE = MemoryCase(
    id="c1",
    turns=[Turn(role="patient", text="t")],
    summary_facts=[
        SummaryFactLabel(id="s1", keywords=["cardiology", "Friday"]),
        SummaryFactLabel(id="s2", keywords=["2.5", "kg"]),
    ],
    semantic_facts=[SemanticFactLabel(key=SemanticKey.transport, keywords=["daughter"])],
    clinical_statements=1,
)


def digest(*facts: tuple[SemanticKey, str]) -> SessionDigest:
    return SessionDigest(episode="e", facts=[SemanticFact(key=k, value=v) for k, v in facts])


def test_all_facts_kept() -> None:
    summary = SessionSummary(summary="Moved cardiology to friday.", key_facts=["Gained 2.5 kg"])
    scores = score_memory([CASE], [summary], [digest((SemanticKey.transport, "Daughter drives"))])
    assert scores.summary_fact_survival == 1.0
    assert scores.semantic_fact_recall == 1.0


def test_lost_summary_fact_is_named() -> None:
    summary = SessionSummary(summary="Moved cardiology to Friday.")
    scores = score_memory([CASE], [summary], [digest()])
    assert scores.lost_summary_facts == ["s2"]
    assert scores.summary_fact_survival == 0.5
    assert scores.missed_semantic_facts == ["c1:transport"]


def test_clinical_fact_is_blocked_not_recalled() -> None:
    clinical = digest((SemanticKey.transport, "daughter brings his insulin"))
    scores = score_memory([CASE], [None], [clinical])
    assert scores.blocked_by_guard == 1
    assert scores.semantic_fact_recall == 0.0
    assert scores.summary_fact_survival == 0.0


def test_memory_cases_load() -> None:
    assert len(load_memory_cases()) == 8


def test_unicode_hyphens_match_plain_hyphen() -> None:
    case = CASE.model_copy(
        update={"summary_facts": [SummaryFactLabel(id="s1", keywords=["x-ray"])]}
    )
    scores = score_memory([case], [SessionSummary(summary="Chest X\u2011ray booked.")], [None])
    assert scores.summary_fact_survival == 1.0
