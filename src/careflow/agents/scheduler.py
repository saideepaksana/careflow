import json
from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from careflow import clock
from careflow.agents.intake import AppointmentAction, IntakeItem, Specialty
from careflow.agents.scheduler_prompt import SCHEDULER_SYSTEM_PROMPT
from careflow.config import CLINIC_TIMEZONE, MORNING_END_HOUR
from careflow.llm.gateway import LLM, complete_structured

PartOfDay = Literal["morning", "afternoon", "any"]


class SchedulingRequest(BaseModel):
    action: AppointmentAction
    appointment_id: str | None = None
    care_plan_item_id: str | None = None
    specialty: Specialty | None = None
    earliest_date: date | None = None
    latest_date: date | None = None
    part_of_day: PartOfDay = "any"


class SchedulingPlan(BaseModel):
    action: AppointmentAction
    appointment_id: str | None = None
    care_plan_item_id: str | None = None
    specialty: Specialty | None = None
    slot_id: str | None = None
    starts_at: datetime | None = None
    clinician_name: str | None = None


def build_scheduler_prompt(
    item: IntakeItem,
    plan_items: list[dict],
    appointments: list[dict],
    memories: list[str],
    feedback: str,
) -> str:
    return (
        f"Today is {clock.today().isoformat()}.\n"
        f"<request>\n{item.model_dump_json(exclude_none=True)}\n</request>\n"
        f"<care_plan>\n{json.dumps(plan_items, default=str)}\n</care_plan>\n"
        f"<appointments>\n{json.dumps(appointments, default=str)}\n</appointments>\n"
        f"<preferences>\n{chr(10).join(memories)}\n</preferences>\n"
        f"<feedback>\n{feedback}\n</feedback>"
    )


def interpret_request(
    llm: LLM,
    item: IntakeItem,
    plan_items: list[dict],
    appointments: list[dict],
    memories: list[str],
    feedback: str,
) -> SchedulingRequest:
    prompt = build_scheduler_prompt(item, plan_items, appointments, memories, feedback)
    return complete_structured(llm, SCHEDULER_SYSTEM_PROMPT, prompt, SchedulingRequest)


def local_hour(starts_at: datetime) -> int:
    return starts_at.astimezone(ZoneInfo(CLINIC_TIMEZONE)).hour


def fits_part_of_day(starts_at: datetime, part_of_day: PartOfDay) -> bool:
    if part_of_day == "any":
        return True
    is_morning = local_hour(starts_at) < MORNING_END_HOUR
    return is_morning == (part_of_day == "morning")


def choose_slot(request: SchedulingRequest, slots: list[dict]) -> dict | None:
    """First free slot, in time order, that fits the requested part of the day."""
    fitting = [slot for slot in slots if fits_part_of_day(slot["starts_at"], request.part_of_day)]
    return fitting[0] if fitting else None
