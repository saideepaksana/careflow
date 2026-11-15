from mcp.server.mcpserver import MCPServer

from careflow.agents.intake import Urgency
from careflow.db import repository
from careflow.db.connection import Connection
from careflow.mcp_servers.records import LOG_LEVEL, error

TASK_KINDS = ("escalation", "approval", "handoff")


def actions_server(conn: Connection, patient_id: str) -> MCPServer:
    """Write tools, bound to the session's patient; every write is keyed for idempotency."""
    server = MCPServer("actions", log_level=LOG_LEVEL)

    @server.tool()
    def book_appointment(
        slot_id: str, idempotency_key: str, care_plan_item_id: str | None = None
    ) -> dict:
        """Book a free slot, optionally for a care-plan item."""
        return repository.book_appointment(
            conn, patient_id, slot_id, care_plan_item_id, idempotency_key
        )

    @server.tool()
    def reschedule_appointment(appointment_id: str, new_slot_id: str, idempotency_key: str) -> dict:
        """Move a booked appointment to a new free slot."""
        return repository.reschedule_appointment(
            conn, patient_id, appointment_id, new_slot_id, idempotency_key
        )

    @server.tool()
    def cancel_appointment(appointment_id: str, idempotency_key: str) -> dict:
        """Cancel a booked appointment."""
        return repository.cancel_appointment(conn, patient_id, appointment_id, idempotency_key)

    @server.tool()
    def create_coordinator_task(
        priority: Urgency,
        title: str,
        detail: str,
        idempotency_key: str,
        kind: str = "handoff",
        thread_id: str | None = None,
    ) -> dict:
        """Ask a nurse coordinator to follow up with the patient."""
        if kind not in TASK_KINDS:
            return error("invalid_kind")
        if thread_id and repository.thread_patient(conn, thread_id) != patient_id:
            return error("invalid_thread")
        return repository.create_coordinator_task(
            conn, patient_id, priority.value, title, detail, idempotency_key, kind, thread_id
        )

    @server.tool()
    def resolve_task(task_id: int, note: str = "") -> dict:
        """Resolve one of the patient's open coordinator tasks."""
        task = repository.get_task(conn, task_id)
        if task is None or task["patient_id"] != patient_id:
            return error("not_found")
        repository.resolve_task(conn, task_id, note)
        return {"ok": True, "task_id": task_id}

    return server
