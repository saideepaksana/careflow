from careflow.agents.intake import AppointmentAction
from careflow.agents.scheduler import SchedulingPlan
from careflow.agents.tools import idempotency_key
from careflow.db import repository
from careflow.db.connection import Connection
from careflow.safety.verifier import VerdictKind, verify_plan


def write_plan(conn: Connection, patient_id: str, plan: SchedulingPlan, key: str) -> dict:
    if plan.action == AppointmentAction.book:
        return repository.book_appointment(
            conn, patient_id, plan.slot_id, plan.care_plan_item_id, key
        )
    if plan.action == AppointmentAction.reschedule:
        return repository.reschedule_appointment(
            conn, patient_id, plan.appointment_id, plan.slot_id, key
        )
    return repository.cancel_appointment(conn, patient_id, plan.appointment_id, key)


def execute_plan(
    conn: Connection,
    patient_id: str,
    thread_id: str,
    plan: SchedulingPlan,
    coordinator_approved: bool,
) -> dict:
    """The workflow's only appointment writer: replays a stored result, else re-verifies."""
    key = idempotency_key(thread_id, plan.action.value, plan)
    stored = repository.get_action_result(conn, key)
    if stored is not None:
        return stored
    verdict = verify_plan(conn, patient_id, plan)
    allowed = verdict.kind == VerdictKind.APPROVED or (
        verdict.kind == VerdictKind.NEEDS_APPROVAL and coordinator_approved
    )
    if not allowed:
        return {"ok": False, "error": verdict.reason}
    return write_plan(conn, patient_id, plan, key)


def create_task(
    conn: Connection,
    patient_id: str,
    key: str,
    kind: str,
    priority: str,
    title: str,
    detail: str,
    thread_id: str | None,
) -> dict:
    return repository.create_coordinator_task(
        conn, patient_id, priority, title, detail, key, kind, thread_id
    )


def resolve_task(conn: Connection, task_id: int, note: str) -> None:
    repository.resolve_task(conn, task_id, note)
