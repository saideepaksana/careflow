from collections.abc import Callable
from datetime import date

import psycopg
from psycopg.types.json import Jsonb

from careflow.config import CLINIC_TIMEZONE, FREE_SLOTS_LIMIT


class ActionRejected(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def get_current_care_plan(conn: psycopg.Connection, patient_id: str) -> dict | None:
    plan = conn.execute(
        "SELECT * FROM care_plans WHERE patient_id = %s AND status = 'published'",
        (patient_id,),
    ).fetchone()
    if plan is None:
        return None
    items = conn.execute(
        "SELECT * FROM care_plan_items WHERE care_plan_id = %s ORDER BY id",
        (plan["id"],),
    ).fetchall()
    return {**plan, "items": items}


def list_appointments(conn: psycopg.Connection, patient_id: str) -> list[dict]:
    return conn.execute(
        "SELECT a.id, a.slot_id, s.starts_at, c.name AS clinician_name, c.specialty,"
        " a.care_plan_item_id FROM appointments a"
        " JOIN slots s ON s.id = a.slot_id JOIN clinicians c ON c.id = s.clinician_id"
        " WHERE a.patient_id = %s AND a.status = 'booked' ORDER BY s.starts_at",
        (patient_id,),
    ).fetchall()


def find_free_slots(
    conn: psycopg.Connection, specialty: str, start_date: date, end_date: date
) -> list[dict]:
    return conn.execute(
        "SELECT s.id, s.starts_at, c.name AS clinician_name FROM slots s"
        " JOIN clinicians c ON c.id = s.clinician_id"
        " WHERE c.specialty = %s AND (s.starts_at AT TIME ZONE %s)::date BETWEEN %s AND %s"
        " AND NOT EXISTS (SELECT 1 FROM appointments a"
        " WHERE a.slot_id = s.id AND a.status = 'booked')"
        " ORDER BY s.starts_at, s.id LIMIT %s",
        (specialty, CLINIC_TIMEZONE, start_date, end_date, FREE_SLOTS_LIMIT),
    ).fetchall()


def run_action(
    conn: psycopg.Connection,
    patient_id: str,
    action: str,
    idempotency_key: str,
    work: Callable[[], dict],
) -> dict:
    stored = conn.execute(
        "SELECT result FROM action_results WHERE idempotency_key = %s", (idempotency_key,)
    ).fetchone()
    if stored is not None:
        return {**stored["result"], "replayed": True}
    try:
        with conn.transaction():
            result = {"ok": True, **work(), "replayed": False}
            conn.execute(
                "INSERT INTO action_results (idempotency_key, patient_id, action, result)"
                " VALUES (%s, %s, %s, %s)",
                (idempotency_key, patient_id, action, Jsonb(result)),
            )
    except ActionRejected as rejection:
        return {"ok": False, "error": rejection.code}
    return result


def next_appointment_id(conn: psycopg.Connection) -> str:
    row = conn.execute(
        "SELECT coalesce(max(substring(id FROM 2)::int), 0) + 1 AS n FROM appointments"
    ).fetchone()
    return f"A{row['n']:03d}"


def is_current_plan_item(conn: psycopg.Connection, patient_id: str, item_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM care_plan_items i JOIN care_plans p ON p.id = i.care_plan_id"
        " WHERE i.id = %s AND p.patient_id = %s AND p.status = 'published'",
        (item_id, patient_id),
    ).fetchone()
    return row is not None


def insert_booking(
    conn: psycopg.Connection,
    patient_id: str,
    slot_id: str,
    care_plan_item_id: str | None,
    idempotency_key: str,
) -> dict:
    slot = conn.execute("SELECT starts_at FROM slots WHERE id = %s", (slot_id,)).fetchone()
    if slot is None:
        raise ActionRejected("slot_not_found")
    if care_plan_item_id and not is_current_plan_item(conn, patient_id, care_plan_item_id):
        raise ActionRejected("item_not_found")
    appointment_id = next_appointment_id(conn)
    try:
        with conn.transaction():
            conn.execute(
                "INSERT INTO appointments (id, patient_id, slot_id, care_plan_item_id, status,"
                " idempotency_key) VALUES (%s, %s, %s, %s, 'booked', %s)",
                (appointment_id, patient_id, slot_id, care_plan_item_id, idempotency_key),
            )
    except psycopg.errors.UniqueViolation as violation:
        if violation.diag.constraint_name != "one_booking_per_slot":
            raise
        raise ActionRejected("slot_taken") from violation
    return {"appointment_id": appointment_id, "starts_at": slot["starts_at"].isoformat()}


def cancel_booking(conn: psycopg.Connection, patient_id: str, appointment_id: str) -> dict:
    row = conn.execute(
        "SELECT status, care_plan_item_id FROM appointments WHERE id = %s AND patient_id = %s",
        (appointment_id, patient_id),
    ).fetchone()
    if row is None:
        raise ActionRejected("not_found")
    if row["status"] != "booked":
        raise ActionRejected("invalid_state")
    conn.execute("UPDATE appointments SET status = 'cancelled' WHERE id = %s", (appointment_id,))
    return row


def book_appointment(
    conn: psycopg.Connection,
    patient_id: str,
    slot_id: str,
    care_plan_item_id: str | None,
    idempotency_key: str,
) -> dict:
    def work() -> dict:
        booking = insert_booking(conn, patient_id, slot_id, care_plan_item_id, idempotency_key)
        return {**booking, "slot_id": slot_id}

    return run_action(conn, patient_id, "book_appointment", idempotency_key, work)


def cancel_appointment(
    conn: psycopg.Connection, patient_id: str, appointment_id: str, idempotency_key: str
) -> dict:
    def work() -> dict:
        cancel_booking(conn, patient_id, appointment_id)
        return {"appointment_id": appointment_id, "status": "cancelled"}

    return run_action(conn, patient_id, "cancel_appointment", idempotency_key, work)


def reschedule_appointment(
    conn: psycopg.Connection,
    patient_id: str,
    appointment_id: str,
    new_slot_id: str,
    idempotency_key: str,
) -> dict:
    def work() -> dict:
        old = cancel_booking(conn, patient_id, appointment_id)
        item_id = old["care_plan_item_id"]
        booking = insert_booking(conn, patient_id, new_slot_id, item_id, idempotency_key)
        return {**booking, "old_appointment_id": appointment_id}

    return run_action(conn, patient_id, "reschedule_appointment", idempotency_key, work)


def create_coordinator_task(
    conn: psycopg.Connection,
    patient_id: str,
    priority: str,
    title: str,
    detail: str,
    idempotency_key: str,
) -> dict:
    def work() -> dict:
        row = conn.execute(
            "INSERT INTO coordinator_tasks (patient_id, priority, status, title, detail,"
            " idempotency_key) VALUES (%s, %s, 'open', %s, %s, %s) RETURNING id",
            (patient_id, priority, title, Jsonb({"text": detail}), idempotency_key),
        ).fetchone()
        return {"task_id": row["id"]}

    return run_action(conn, patient_id, "create_coordinator_task", idempotency_key, work)


def insert_audit_event(
    conn: psycopg.Connection, patient_id: str, actor: str, event: str, detail: dict
) -> None:
    conn.execute(
        "INSERT INTO audit_events (patient_id, actor, event, detail) VALUES (%s, %s, %s, %s)",
        (patient_id, actor, event, Jsonb(detail)),
    )


def list_patients(conn: psycopg.Connection) -> list[dict]:
    return conn.execute("SELECT id, name FROM patients ORDER BY id").fetchall()


def get_patient(conn: psycopg.Connection, patient_id: str) -> dict | None:
    return conn.execute("SELECT id, name FROM patients WHERE id = %s", (patient_id,)).fetchone()


def create_conversation(conn: psycopg.Connection, conversation_id: str, patient_id: str) -> None:
    conn.execute(
        "INSERT INTO conversations (id, patient_id) VALUES (%s, %s)",
        (conversation_id, patient_id),
    )


def owns_conversation(conn: psycopg.Connection, conversation_id: str, patient_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM conversations WHERE id = %s AND patient_id = %s",
        (conversation_id, patient_id),
    ).fetchone()
    return row is not None


def list_messages(conn: psycopg.Connection, conversation_id: str) -> list[dict]:
    return conn.execute(
        "SELECT role, content, created_at FROM messages WHERE conversation_id = %s ORDER BY id",
        (conversation_id,),
    ).fetchall()


def insert_message(conn: psycopg.Connection, conversation_id: str, role: str, content: str) -> None:
    conn.execute(
        "INSERT INTO messages (conversation_id, role, content) VALUES (%s, %s, %s)",
        (conversation_id, role, content),
    )
