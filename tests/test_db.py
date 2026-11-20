import psycopg
import pytest

from careflow.db import repository
from careflow.db.repository import get_current_care_plan


@pytest.mark.parametrize(
    ("table", "count"),
    [
        ("patients", 5),
        ("encounters", 5),
        ("care_plans", 6),
        ("clinicians", 9),
        ("slots", 9 * 15 * 4),
        ("appointments", 2),
    ],
)
def test_seed_row_counts(db: psycopg.Connection, table: str, count: int) -> None:
    assert db.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"] == count


def test_current_care_plan_is_latest_published(db: psycopg.Connection) -> None:
    plan = get_current_care_plan(db, "P001")
    assert plan["version"] == 2
    assert len(plan["items"]) == 6


def test_slot_cannot_be_double_booked(db: psycopg.Connection) -> None:
    slot = db.execute("SELECT slot_id FROM appointments WHERE id = 'A001'").fetchone()["slot_id"]
    with pytest.raises(psycopg.errors.UniqueViolation):
        db.execute(
            "INSERT INTO appointments (id, patient_id, slot_id, status, idempotency_key)"
            " VALUES ('A900', 'P002', %s, 'booked', 'k-900')",
            (slot,),
        )


def test_idempotency_key_is_unique(db: psycopg.Connection) -> None:
    with pytest.raises(psycopg.errors.UniqueViolation):
        db.execute(
            "INSERT INTO appointments (id, patient_id, slot_id, status, idempotency_key)"
            " SELECT 'A901', 'P002', id, 'booked', 'seed-A001' FROM slots"
            " WHERE id NOT IN (SELECT slot_id FROM appointments) LIMIT 1"
        )


def test_only_one_published_plan_per_patient(db: psycopg.Connection) -> None:
    with pytest.raises(psycopg.errors.UniqueViolation):
        db.execute(
            "INSERT INTO care_plans VALUES"
            " ('CP001-v3', 'P001', 'E001', 3, 'published', '2026-11-02')"
        )


def test_only_one_pending_confirmation_per_conversation(db: psycopg.Connection) -> None:
    db.execute("INSERT INTO conversations (id, patient_id) VALUES ('conv-db', 'P001')")
    for thread_id in ("conv-db:1", "conv-db:2"):
        db.execute(
            "INSERT INTO workflow_runs (thread_id, conversation_id, status)"
            " VALUES (%s, 'conv-db', 'running')",
            (thread_id,),
        )
    await_confirmation = (
        "UPDATE workflow_runs SET status = 'awaiting_confirmation' WHERE thread_id = %s"
    )
    db.execute(await_confirmation, ("conv-db:1",))
    with pytest.raises(psycopg.errors.UniqueViolation):
        db.execute(await_confirmation, ("conv-db:2",))


def test_checkpoint_tables_exist(db: psycopg.Connection) -> None:
    row = db.execute("SELECT to_regclass('public.checkpoints') AS name").fetchone()
    assert row["name"] == "checkpoints"


def test_stale_runs_skip_runs_still_in_flight(db: psycopg.Connection) -> None:
    repository.create_conversation(db, "conv-stale", "P001")
    repository.create_workflow_run(db, "conv-stale:1", "conv-stale")
    assert repository.stale_runs(db, "running", 60) == []
    assert repository.stale_runs(db, "running", 0) == ["conv-stale:1"]
