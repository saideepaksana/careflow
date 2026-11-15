import psycopg
import pytest

from careflow.db import repository
from careflow.memory.embeddings import FakeEmbedder
from careflow.memory.manager import (
    MemoryWriteResult,
    SemanticFact,
    SemanticKey,
    SessionDigest,
    recall,
    write_session_memory,
)

EMBEDDER = FakeEmbedder()


@pytest.fixture
def conversation(db: psycopg.Connection) -> str:
    repository.create_conversation(db, "conv-mem", "P001")
    repository.create_conversation(db, "conv-other", "P002")
    return "conv-mem"


def write(
    db: psycopg.Connection, episode: str, facts: list[tuple[str, str]], patient: str = "P001"
) -> MemoryWriteResult:
    digest = SessionDigest(
        episode=episode, facts=[SemanticFact(key=key, value=value) for key, value in facts]
    )
    conversation_id = "conv-mem" if patient == "P001" else "conv-other"
    return write_session_memory(db, EMBEDDER, patient, conversation_id, digest)


def active(db: psycopg.Connection) -> dict[str, str]:
    rows = repository.active_semantic_memories(db, "P001")
    return {row["key"]: row["content"] for row in rows}


def test_episode_is_written(db: psycopg.Connection, conversation: str) -> None:
    result = write(db, "Moved cardiology to Friday.", [])
    row = db.execute(
        "SELECT type, content, embedding IS NOT NULL AS has_vector FROM memories WHERE id = %s",
        (result.episode_id,),
    ).fetchone()
    assert row["type"] == "episodic"
    assert row["content"].endswith("Moved cardiology to Friday.")
    assert row["has_vector"]


def test_new_value_supersedes_old(db: psycopg.Connection, conversation: str) -> None:
    first = write(db, "e1", [(SemanticKey.preferred_time_of_day, "mornings")])
    second = write(db, "e2", [(SemanticKey.preferred_time_of_day, "afternoons")])
    assert active(db) == {"preferred_time_of_day": "afternoons"}
    assert second.superseded == first.written


def test_same_value_is_a_duplicate(db: psycopg.Connection, conversation: str) -> None:
    write(db, "e1", [(SemanticKey.transport, "Daughter drives")])
    result = write(db, "e2", [(SemanticKey.transport, " daughter drives ")])
    assert result.duplicates == 1
    assert result.written == []


def test_clinical_value_is_rejected_and_audited(db: psycopg.Connection, conversation: str) -> None:
    result = write(db, "e1", [(SemanticKey.caregiver, "wife manages his insulin")])
    event = db.execute(
        "SELECT detail FROM audit_events WHERE event = 'memory_rejected' ORDER BY id DESC"
    ).fetchone()
    assert result.rejected_clinical == 1
    assert active(db) == {}
    assert event["detail"] == {"key": "caregiver"}


def test_recall_returns_facts_and_nearest_episode(
    db: psycopg.Connection, conversation: str
) -> None:
    write(db, "Rescheduled the lab test to Thursday.", [(SemanticKey.transport, "bus")])
    write(db, "Asked about cardiology parking.", [])
    write(db, "Asked about the lab test fasting rules.", [], patient="P002")
    lines = recall(db, EMBEDDER, "P001", "when is my lab test")
    assert lines[0] == "transport: bus"
    assert "Rescheduled the lab test to Thursday." in lines[1]
    assert not any("fasting" in line for line in lines)
