import json

from careflow.agents.careplan_prompt import CAREPLAN_SYSTEM_PROMPT
from careflow.agents.intake_prompt import INTAKE_SYSTEM_PROMPT
from careflow.agents.scheduler_prompt import SCHEDULER_SYSTEM_PROMPT
from careflow.memory.prompts import DIGEST_SYSTEM_PROMPT

ROLES = {
    INTAKE_SYSTEM_PROMPT: "intake",
    SCHEDULER_SYSTEM_PROMPT: "planner",
    CAREPLAN_SYSTEM_PROMPT: "careplan",
    DIGEST_SYSTEM_PROMPT: "digest",
}


class RoleLLM:
    """Answers by which agent is calling, so a node re-run after a crash gets the same reply."""

    def __init__(self, replies: dict[str, str]) -> None:
        self.replies = replies
        self.calls: list[str] = []

    def complete(self, system: str, user: str) -> str:
        role = ROLES[system]
        self.calls.append(role)
        return self.replies[role]


def intake_reply(items: list[dict], urgency: str = "routine") -> str:
    return json.dumps({"items": items, "urgency": urgency})


def question(summary: str) -> dict:
    return {"kind": "care_plan_question", "summary": summary}


def appointment(action: str, summary: str) -> dict:
    return {"kind": "appointment_request", "summary": summary, "appointment_action": action}


def planner_reply(action: str, day: str, **fields: str) -> str:
    request = {"action": action, "earliest_date": day, "latest_date": day, **fields}
    return json.dumps(request)


def cited_answer(text: str) -> str:
    return json.dumps({"covered": True, "sentences": [{"text": text, "sources": ["S1"]}]})


def book_lab(day: str) -> dict[str, str]:
    return {
        "intake": intake_reply([appointment("book", "Book the blood test")]),
        "planner": planner_reply("book", day, care_plan_item_id="CP001-v2-02"),
    }
