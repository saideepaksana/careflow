from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

from careflow import clock
from careflow.agents.intake import Turn
from careflow.config import EPISODE_MAX_CHARS, MEMORY_VALUE_MAX_CHARS, RECALL_EPISODES
from careflow.db import repository
from careflow.db.connection import Connection
from careflow.llm.gateway import LLM, complete_structured
from careflow.memory.embeddings import Embedder
from careflow.memory.prompts import DIGEST_SYSTEM_PROMPT
from careflow.memory.working import SessionSummary, format_turns, render_summary
from careflow.safety.memory_guard import is_clinical

AUDIT_ACTOR = "memory_manager"


class SemanticKey(StrEnum):
    preferred_days = "preferred_days"
    preferred_time_of_day = "preferred_time_of_day"
    preferred_clinician = "preferred_clinician"
    transport = "transport"
    caregiver = "caregiver"
    contact_method = "contact_method"
    contact_time = "contact_time"
    accessibility_need = "accessibility_need"


class SemanticFact(BaseModel):
    key: SemanticKey
    value: str = Field(min_length=1, max_length=MEMORY_VALUE_MAX_CHARS)


class SessionDigest(BaseModel):
    episode: str
    facts: list[SemanticFact] = []

    @field_validator("episode", mode="before")
    @classmethod
    def truncate_episode(cls, value: object) -> object:
        return value[:EPISODE_MAX_CHARS] if isinstance(value, str) else value


class MemoryWriteResult(BaseModel):
    episode_id: int = 0
    written: list[int] = []
    superseded: list[int] = []
    duplicates: int = 0
    rejected_clinical: int = 0


def digest_session(llm: LLM, summary: SessionSummary | None, turns: list[Turn]) -> SessionDigest:
    prompt = (
        f"<session_summary>\n{render_summary(summary)}\n</session_summary>\n"
        f"<turns>\n{format_turns(turns)}\n</turns>"
    )
    return complete_structured(llm, DIGEST_SYSTEM_PROMPT, prompt, SessionDigest)


def same_value(left: str, right: str) -> bool:
    return left.strip().lower() == right.strip().lower()


def write_fact(
    conn: Connection,
    embedder: Embedder,
    patient_id: str,
    conversation_id: str,
    fact: SemanticFact,
    result: MemoryWriteResult,
) -> None:
    if is_clinical(fact.value):
        result.rejected_clinical += 1
        repository.insert_audit_event(
            conn, patient_id, AUDIT_ACTOR, "memory_rejected", {"key": fact.key.value}
        )
        return
    active = {row["key"]: row for row in repository.active_semantic_memories(conn, patient_id)}
    current = active.get(fact.key.value)
    if current is not None and same_value(current["content"], fact.value):
        result.duplicates += 1
        return
    embedding = embedder.embed([f"{fact.key.value}: {fact.value}"])[0]
    if current is None:
        result.written.append(
            repository.insert_memory(
                conn, patient_id, "semantic", fact.key.value, fact.value, conversation_id, embedding
            )
        )
        return
    result.written.append(
        replace_fact(conn, patient_id, conversation_id, fact, current["id"], embedding)
    )
    result.superseded.append(current["id"])


def replace_fact(
    conn: Connection,
    patient_id: str,
    conversation_id: str,
    fact: SemanticFact,
    old_id: int,
    embedding: list[float],
) -> int:
    # The old row must leave the one-active-per-key index before the new row exists,
    # so it points at itself first and at its replacement once that has an id.
    repository.supersede_memory(conn, old_id, old_id)
    new_id = repository.insert_memory(
        conn, patient_id, "semantic", fact.key.value, fact.value, conversation_id, embedding
    )
    repository.supersede_memory(conn, old_id, new_id)
    return new_id


def write_session_memory(
    conn: Connection,
    embedder: Embedder,
    patient_id: str,
    conversation_id: str,
    digest: SessionDigest,
) -> MemoryWriteResult:
    result = MemoryWriteResult()
    with conn.transaction():
        episode = f"{clock.today().isoformat()}: {digest.episode}"
        embedding = embedder.embed([episode])[0]
        result.episode_id = repository.insert_memory(
            conn, patient_id, "episodic", None, episode, conversation_id, embedding
        )
        for fact in digest.facts:
            write_fact(conn, embedder, patient_id, conversation_id, fact, result)
    return result


def recall(conn: Connection, embedder: Embedder, patient_id: str, query: str) -> list[str]:
    facts = [
        f"{row['key']}: {row['content']}"
        for row in repository.active_semantic_memories(conn, patient_id)
    ]
    embedding = embedder.embed([query])[0]
    episodes = repository.nearest_episodes(conn, patient_id, embedding, RECALL_EPISODES)
    return facts + [f"Past session: {row['content']}" for row in episodes]
