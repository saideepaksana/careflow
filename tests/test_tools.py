from datetime import date

import psycopg
import pytest

from careflow.agents.tools import PatientTools


@pytest.fixture
def tools(db: psycopg.Connection) -> PatientTools:
    return PatientTools(db, "P001", "conv-test")


def free_slot(tools: PatientTools, specialty: str = "cardiology") -> str:
    args = {"specialty": specialty, "start_date": "2026-11-03", "end_date": "2026-11-20"}
    return tools.call_tool("find_slots", args)["data"][0]["id"]


def audit_count(db: psycopg.Connection) -> int:
    return db.execute("SELECT count(*) AS n FROM audit_events").fetchone()["n"]


def test_find_slots_returns_free_slots_of_specialty(tools: PatientTools) -> None:
    args = {"specialty": "cardiology", "start_date": "2026-11-03", "end_date": "2026-11-20"}
    slots = tools.call_tool("find_slots", args)["data"]
    booked = tools.call_tool("list_appointments", {})["data"][0]["slot_id"]
    assert slots
    assert booked not in {slot["id"] for slot in slots}
    assert all(slot["clinician_name"] in {"Dr. Anil Verma", "Dr. Priya Nair"} for slot in slots)


def test_find_slots_respects_dates(tools: PatientTools) -> None:
    args = {"specialty": "cardiology", "start_date": "2026-11-10", "end_date": "2026-11-10"}
    slots = tools.call_tool("find_slots", args)["data"]
    assert {date.fromisoformat(slot["starts_at"][:10]) for slot in slots} == {date(2026, 11, 10)}


def test_same_booking_twice_is_replayed(tools: PatientTools, db: psycopg.Connection) -> None:
    args = {"slot_id": free_slot(tools)}
    first = tools.call_tool("book_appointment", args)
    second = tools.call_tool("book_appointment", args)
    count = db.execute(
        "SELECT count(*) AS n FROM appointments WHERE slot_id = %s", (args["slot_id"],)
    ).fetchone()["n"]
    assert first["ok"] and not first["replayed"]
    assert second["replayed"]
    assert second["appointment_id"] == first["appointment_id"]
    assert count == 1


def test_taken_slot_is_rejected(db: psycopg.Connection) -> None:
    slot = free_slot(PatientTools(db, "P001", "conv-a"))
    PatientTools(db, "P001", "conv-a").call_tool("book_appointment", {"slot_id": slot})
    result = PatientTools(db, "P002", "conv-b").call_tool("book_appointment", {"slot_id": slot})
    assert result == {"ok": False, "error": "slot_taken"}


def test_cannot_cancel_other_patients_appointment(db: psycopg.Connection) -> None:
    tools = PatientTools(db, "P002", "conv-test")
    result = tools.call_tool("cancel_appointment", {"appointment_id": "A001"})
    assert result == {"ok": False, "error": "not_found"}


def test_reschedule_moves_booking(tools: PatientTools) -> None:
    old_slot = tools.call_tool("list_appointments", {})["data"][0]["slot_id"]
    new_slot = free_slot(tools)
    result = tools.call_tool(
        "reschedule_appointment", {"appointment_id": "A001", "new_slot_id": new_slot}
    )
    booked = {row["slot_id"] for row in tools.call_tool("list_appointments", {})["data"]}
    assert result["ok"]
    assert booked == {new_slot}
    assert old_slot not in booked


@pytest.mark.parametrize(
    ("name", "args", "error"),
    [
        ("list_appointments", {"patient_id": "P002"}, "invalid_args"),
        ("book_appointment", {"slot_id": "S-1", "patient_id": "P002"}, "invalid_args"),
        ("delete_everything", {}, "unknown_tool"),
        ("book_appointment", {"slot_id": "S-missing"}, "slot_not_found"),
    ],
)
def test_rejected_calls(tools: PatientTools, name: str, args: dict, error: str) -> None:
    assert tools.call_tool(name, args)["error"] == error


def test_every_call_is_audited(tools: PatientTools, db: psycopg.Connection) -> None:
    before = audit_count(db)
    tools.call_tool("get_care_plan", {})
    tools.call_tool("delete_everything", {})
    assert audit_count(db) == before + 2
