from datetime import date
from enum import StrEnum
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from careflow import clock
from careflow.agents.intake import AppointmentAction
from careflow.agents.scheduler import SchedulingPlan
from careflow.config import CLINIC_TIMEZONE
from careflow.db import repository
from careflow.db.connection import Connection

BOOKABLE_KINDS = ("follow_up", "lab")


class VerdictKind(StrEnum):
    APPROVED = "approved"
    NEEDS_APPROVAL = "needs_approval"
    REJECTED = "rejected"


class Verdict(BaseModel):
    kind: VerdictKind
    reason: str
    fixable: bool = False


def rejected(reason: str, fixable: bool = False) -> Verdict:
    return Verdict(kind=VerdictKind.REJECTED, reason=reason, fixable=fixable)


def slot_date(slot: dict) -> date:
    return slot["starts_at"].astimezone(ZoneInfo(CLINIC_TIMEZONE)).date()


def slot_problem(plan: SchedulingPlan, slot: dict | None, specialty: str | None) -> Verdict | None:
    if plan.slot_id is None:
        return rejected("no_free_slot")
    if slot is None or slot["booked"] or slot_date(slot) <= clock.today():
        return rejected("slot_taken", fixable=True)
    if specialty and slot["specialty"] != specialty:
        return rejected("specialty_mismatch", fixable=True)
    return None


def verify_booking(
    conn: Connection, patient_id: str, plan: SchedulingPlan, moving: str | None = None
) -> Verdict:
    item = None
    if plan.care_plan_item_id:
        item = repository.get_plan_item(conn, patient_id, plan.care_plan_item_id)
        if item is None or item["kind"] not in BOOKABLE_KINDS:
            return rejected("item_not_in_plan", fixable=True)
    slot = repository.get_slot(conn, plan.slot_id) if plan.slot_id else None
    problem = slot_problem(plan, slot, item["specialty"] if item else plan.specialty)
    if problem:
        return problem
    if item is None:
        return Verdict(kind=VerdictKind.NEEDS_APPROVAL, reason="not_in_plan")
    booked = repository.booked_appointment_for_item(conn, patient_id, item["id"])
    if booked and booked != moving:
        return rejected("already_booked")
    if slot_date(slot) > item["due_date"]:
        return Verdict(kind=VerdictKind.NEEDS_APPROVAL, reason="past_due_date")
    return Verdict(kind=VerdictKind.APPROVED, reason="in_plan")


def booked_appointment(conn: Connection, patient_id: str, plan: SchedulingPlan) -> dict | None:
    if plan.appointment_id is None:
        return None
    appointment = repository.get_appointment(conn, patient_id, plan.appointment_id)
    return appointment if appointment and appointment["status"] == "booked" else None


def verify_plan(conn: Connection, patient_id: str, plan: SchedulingPlan) -> Verdict:
    """Deterministic checks of a scheduling plan against the care plan and current bookings."""
    if plan.action == AppointmentAction.book:
        return verify_booking(conn, patient_id, plan)
    appointment = booked_appointment(conn, patient_id, plan)
    if appointment is None:
        return rejected("appointment_not_found", fixable=True)
    if plan.action == AppointmentAction.reschedule:
        moved = plan.model_copy(update={"care_plan_item_id": appointment["care_plan_item_id"]})
        return verify_booking(conn, patient_id, moved, moving=appointment["id"])
    if appointment["care_plan_item_id"]:
        return Verdict(kind=VerdictKind.NEEDS_APPROVAL, reason="cancels_plan_item")
    return Verdict(kind=VerdictKind.APPROVED, reason="cancel")
