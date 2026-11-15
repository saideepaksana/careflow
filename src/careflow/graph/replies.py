from zoneinfo import ZoneInfo

from careflow.agents.intake import AppointmentAction
from careflow.agents.scheduler import SchedulingPlan
from careflow.config import CLINIC_TIMEZONE

EMERGENCY_REPLY = "This may be an emergency. Call 112 now. I have alerted your care team."
URGENT_REPLY = (
    "A nurse from your care team will call you today about this. If it gets worse, call 112."
)
SCOPE_REPLY = "I can help with your appointments and with questions about your care plan."
ONE_CHANGE_REPLY = "I can make one appointment change at a time. Let's start with this one."
APPROVAL_PENDING_REPLY = (
    "Thanks. This change is outside your care plan, so I've asked your care team to approve it. "
    "I'll let you know here when they reply."
)
NOT_CHANGED_REPLY = "Okay, I haven't changed anything."
UNAVAILABLE_REPLY = (
    "CareFlow is unavailable right now. If this is urgent, call your care team. "
    "In an emergency, call 112."
)
REJECTION_REPLIES = {
    "already_booked": "You already have that visit booked. I can move it to another time instead.",
    "no_free_slot": "I couldn't find a free slot at that time. Could you suggest another day?",
}
DEFAULT_REJECTION = "I couldn't make that change."
FAILURE_REPLIES = {"slot_taken": "That slot was just taken, so nothing was changed."}
DEFAULT_FAILURE = "I couldn't complete that change, so nothing was changed."


def format_time(plan: SchedulingPlan) -> str:
    if plan.starts_at is None:
        return ""
    local = plan.starts_at.astimezone(ZoneInfo(CLINIC_TIMEZONE))
    return local.strftime("%a %d %b at %H:%M")


def describe_change(plan: SchedulingPlan) -> str:
    specialty = plan.specialty.value.replace("_", " ") if plan.specialty else "the"
    if plan.action == AppointmentAction.cancel:
        return f"cancel appointment {plan.appointment_id}"
    target = f"{specialty} with {plan.clinician_name} on {format_time(plan)}"
    if plan.action == AppointmentAction.reschedule:
        return f"move appointment {plan.appointment_id} to {target}"
    return f"book {target}"


def confirmation_prompt(plan: SchedulingPlan, needs_approval: bool) -> str:
    approval = (
        " This is outside your care plan, so your care team will also need to approve it."
        if needs_approval
        else ""
    )
    return f"I can {describe_change(plan)}.{approval} Shall I go ahead?"


def rejected_reply(reason: str) -> str:
    return REJECTION_REPLIES.get(reason, DEFAULT_REJECTION)


def denied_reply(note: str) -> str:
    reason = f" Their note: {note}" if note else ""
    return f"Your care team did not approve this change, so nothing was changed.{reason}"


def action_done_reply(plan: SchedulingPlan) -> str:
    return f"Done. I did this: {describe_change(plan)}."


def action_failed_reply(error: str) -> str:
    return FAILURE_REPLIES.get(error, DEFAULT_FAILURE)
