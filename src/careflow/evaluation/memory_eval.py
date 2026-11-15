from pathlib import Path

from pydantic import BaseModel

from careflow.agents.intake import Turn
from careflow.memory.manager import SemanticKey, SessionDigest
from careflow.memory.working import SessionSummary, render_summary
from careflow.safety.memory_guard import is_clinical

MEMORY_CASES_PATH = Path(__file__).with_name("data") / "memory_cases.jsonl"
HYPHENS = str.maketrans({"\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-"})


class SummaryFactLabel(BaseModel):
    id: str
    keywords: list[str]


class SemanticFactLabel(BaseModel):
    key: SemanticKey
    keywords: list[str]


class MemoryCase(BaseModel):
    id: str
    turns: list[Turn]
    summary_facts: list[SummaryFactLabel]
    semantic_facts: list[SemanticFactLabel]
    clinical_statements: int


class MemoryScores(BaseModel):
    cases: int
    summary_fact_survival: float
    semantic_fact_recall: float
    blocked_by_guard: int
    lost_summary_facts: list[str]
    missed_semantic_facts: list[str]


def load_memory_cases(path: Path = MEMORY_CASES_PATH) -> list[MemoryCase]:
    lines = path.read_text().splitlines()
    return [MemoryCase.model_validate_json(line) for line in lines if line.strip()]


def contains_all(text: str, keywords: list[str]) -> bool:
    normalized = text.translate(HYPHENS).lower()
    return all(keyword.lower() in normalized for keyword in keywords)


def lost_facts(case: MemoryCase, summary: SessionSummary | None) -> list[str]:
    rendered = render_summary(summary)
    return [fact.id for fact in case.summary_facts if not contains_all(rendered, fact.keywords)]


def missed_facts(case: MemoryCase, digest: SessionDigest | None) -> list[str]:
    kept = [fact for fact in (digest.facts if digest else []) if not is_clinical(fact.value)]
    return [
        f"{case.id}:{label.key.value}"
        for label in case.semantic_facts
        if not any(f.key == label.key and contains_all(f.value, label.keywords) for f in kept)
    ]


def blocked_count(digest: SessionDigest | None) -> int:
    return sum(is_clinical(fact.value) for fact in digest.facts) if digest else 0


def rate(misses: int, total: int) -> float:
    return (total - misses) / total if total else 1.0


def score_memory(
    cases: list[MemoryCase],
    summaries: list[SessionSummary | None],
    digests: list[SessionDigest | None],
) -> MemoryScores:
    lost = [fact for case, s in zip(cases, summaries) for fact in lost_facts(case, s)]
    missed = [fact for case, d in zip(cases, digests) for fact in missed_facts(case, d)]
    return MemoryScores(
        cases=len(cases),
        summary_fact_survival=rate(len(lost), sum(len(c.summary_facts) for c in cases)),
        semantic_fact_recall=rate(len(missed), sum(len(c.semantic_facts) for c in cases)),
        blocked_by_guard=sum(blocked_count(digest) for digest in digests),
        lost_summary_facts=lost,
        missed_semantic_facts=missed,
    )
