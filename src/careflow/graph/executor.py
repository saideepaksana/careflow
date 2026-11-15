from careflow.agents.intake import AppointmentAction
from careflow.agents.scheduler import SchedulingPlan
from careflow.agents.tools import idempotency_key
from careflow.db import repository
from careflow.db.connection import Connection
from careflow.mcp_servers.client import McpTools
from careflow.safety.verifier import VerdictKind, verify_plan


def write_plan(tools: McpTools, plan: SchedulingPlan, key: str) -> dict:
    if plan.action == AppointmentAction.book:
        args = {"slot_id": plan.slot_id, "care_plan_item_id": plan.care_plan_item_id}
        return tools.act("book_appointment", {**args, "idempotency_key": key})
    if plan.action == AppointmentAction.reschedule:
        args = {"appointment_id": plan.appointment_id, "new_slot_id": plan.slot_id}
        return tools.act("reschedule_appointment", {**args, "idempotency_key": key})
    args = {"appointment_id": plan.appointment_id, "idempotency_key": key}
    return tools.act("cancel_appointment", args)


def execute_plan(
    conn: Connection,
    tools: McpTools,
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
    return write_plan(tools, plan, key)


def create_task(
    tools: McpTools,
    key: str,
    kind: str,
    priority: str,
    title: str,
    detail: str,
    thread_id: str | None,
) -> dict:
    args = {"priority": priority, "title": title, "detail": detail, "kind": kind}
    return tools.act(
        "create_coordinator_task", {**args, "idempotency_key": key, "thread_id": thread_id}
    )


def resolve_task(tools: McpTools, task_id: int, note: str) -> dict:
    return tools.act("resolve_task", {"task_id": task_id, "note": note})
