from zoneinfo import ZoneInfo

from careflow.agents.intake import AppointmentAction
from careflow.agents.scheduler import SchedulingPlan
from careflow.config import CLINIC_TIMEZONE

EMERGENCY_REPLY = "This may be an emergency. Call 112 now. I have alerted your care team."
URGENT_REPLY = (
    "A nurse from your care team will call you today about this. If it gets worse, call 112."
)
SCOPE_REPLY = "I can help with your appointments and with questions about your care plan."
ONE_CHANGE_REPLY = (
    "I can make one appointment change at a time, so I'll handle the first one now. "
    "Please send the other change after this one."
)
HELD_CHANGE_REPLY = "I haven't changed your appointments; your care team will help with them."
APPROVAL_PENDING_REPLY = (
    "Thanks. This change is outside your care plan, so I've asked your care team to approve it. "
    "I'll let you know here when they reply."
)
NOT_CHANGED_REPLY = "Okay, I haven't changed anything."
DENIED_REPLY = "Your care team did not approve this change, so nothing was changed."
SPECIALTY_LABELS = {
    "laboratory": "lab test",
    "radiology": "scan",
    "primary_care": "primary care visit",
}
HANDOFF_REPLY = (
    "I've passed this to your care team, and they will follow up with you here. "
    "If this is an emergency, call 112."
)
REJECTION_REPLIES = {
    "already_booked": "You already have that visit booked. I can move it to another time instead.",
    "no_free_slot": "I couldn't find a free slot at that time. Could you suggest another day?",
}
DEFAULT_REJECTION = "I couldn't make that change."
FAILURE_REPLIES = {"slot_taken": "That slot was just taken, so nothing was changed."}
DEFAULT_FAILURE = "I couldn't complete that change, so nothing was changed."


def reason_label(code: str) -> str:
    return code.replace("_", " ").replace(":", ": ")


def escalation_reason(reason: str, sign_names: dict[str, str]) -> str:
    kind, _, value = reason.partition(":")
    if kind == "warning_sign":
        return f"warning sign: {sign_names.get(value, value)}"
    if kind == "red_flag":
        return f'red-flag phrase "{value}"'
    return f"intake rated it {value}"


def format_time(plan: SchedulingPlan) -> str:
    if plan.starts_at is None:
        return ""
    local = plan.starts_at.astimezone(ZoneInfo(CLINIC_TIMEZONE))
    return local.strftime("%a %d %b at %H:%M")


def visit_label(plan: SchedulingPlan) -> str:
    if plan.specialty is None:
        return "appointment"
    return SPECIALTY_LABELS.get(plan.specialty.value, f"{plan.specialty.value} visit")


CHANGE_VERBS = {
    AppointmentAction.book: ("book", "booked"),
    AppointmentAction.reschedule: ("move", "moved"),
    AppointmentAction.cancel: ("cancel", "cancelled"),
}


def describe_change(plan: SchedulingPlan, owner: str = "your", done: bool = False) -> str:
    visit = f"{CHANGE_VERBS[plan.action][done]} {owner} {visit_label(plan)}"
    if plan.action == AppointmentAction.cancel:
        return f"{visit} on {format_time(plan)}" if plan.starts_at else visit
    when = f"{format_time(plan)} with {plan.clinician_name}"
    if plan.action == AppointmentAction.reschedule:
        return f"{visit} to {when}"
    return f"{visit} for {when}"


def confirmation_prompt(plan: SchedulingPlan, needs_approval: bool) -> str:
    approval = (
        " This is outside your care plan, so your care team will also need to approve it."
        if needs_approval
        else ""
    )
    return f"I can {describe_change(plan)}.{approval} Shall I go ahead?"


def rejected_reply(reason: str) -> str:
    return REJECTION_REPLIES.get(reason, DEFAULT_REJECTION)


def action_done_reply(plan: SchedulingPlan) -> str:
    return f"Done. I've {describe_change(plan, done=True)}."


def action_failed_reply(error: str) -> str:
    return FAILURE_REPLIES.get(error, DEFAULT_FAILURE)
