from datetime import date, timedelta

from mcp.server.mcpserver import MCPServer

from careflow.agents.intake import Specialty
from careflow.config import FREE_SLOTS_LIMIT, SLOT_SCAN_LIMIT
from careflow.db import repository
from careflow.db.connection import Connection

LOG_LEVEL = "WARNING"


def ok(data: object) -> dict:
    return {"ok": True, "data": data}


def error(code: str) -> dict:
    return {"ok": False, "error": code}


def with_due_date(item: dict, published_on: date) -> dict:
    days = item["due_within_days"]
    return {**item, "due_date": published_on + timedelta(days=days) if days is not None else None}


def care_plan_view(conn: Connection, patient_id: str) -> dict:
    plan = repository.get_current_care_plan(conn, patient_id)
    if plan is None:
        return error("no_plan")
    items = [with_due_date(item, plan["published_on"]) for item in plan["items"]]
    return ok({**plan, "items": items})


def records_server(conn: Connection, patient_id: str) -> MCPServer:
    """Read-only patient record tools, bound to the session's patient."""
    server = MCPServer("records", log_level=LOG_LEVEL)

    @server.tool()
    def get_care_plan() -> dict:
        """Read the patient's current care plan, with a due date on follow-ups and labs."""
        return care_plan_view(conn, patient_id)

    @server.tool()
    def list_appointments() -> dict:
        """List the patient's booked appointments."""
        return ok(repository.list_appointments(conn, patient_id))

    @server.tool()
    def get_appointment(appointment_id: str) -> dict:
        """Read one of the patient's appointments."""
        appointment = repository.get_appointment(conn, patient_id, appointment_id)
        return ok(appointment) if appointment else error("not_found")

    @server.tool()
    def find_free_slots(
        specialty: Specialty, start_date: date, end_date: date, limit: int = FREE_SLOTS_LIMIT
    ) -> dict:
        """Find free appointment slots for a specialty between two dates."""
        capped = max(1, min(limit, SLOT_SCAN_LIMIT))
        return ok(repository.find_free_slots(conn, specialty.value, start_date, end_date, capped))

    return server
