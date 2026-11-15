from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from careflow.agents.intake import IntakeItem
from careflow.agents.scheduler import SchedulingRequest, build_scheduler_prompt, choose_slot

CLINIC = ZoneInfo("Asia/Kolkata")
SLOTS = [
    {"id": "S-09", "starts_at": datetime(2026, 11, 3, 9, tzinfo=CLINIC)},
    {"id": "S-11", "starts_at": datetime(2026, 11, 3, 11, tzinfo=CLINIC)},
    {"id": "S-14", "starts_at": datetime(2026, 11, 3, 14, tzinfo=CLINIC)},
]


@pytest.mark.parametrize(
    ("part_of_day", "slots", "expected"),
    [
        ("any", SLOTS, "S-09"),
        ("morning", SLOTS, "S-09"),
        ("afternoon", SLOTS, "S-14"),
        ("afternoon", SLOTS[:2], None),
        ("morning", [], None),
    ],
)
def test_choose_slot(part_of_day: str, slots: list[dict], expected: str | None) -> None:
    request = SchedulingRequest(action="book", part_of_day=part_of_day)
    chosen = choose_slot(request, slots)
    assert (chosen["id"] if chosen else None) == expected


def test_planner_prompt_tags_inputs_as_data() -> None:
    item = IntakeItem(kind="appointment_request", summary="Book it", appointment_action="book")
    prompt = build_scheduler_prompt(item, [{"id": "CP001-v2-02"}], [], ["mornings"], "slot_taken")
    for tag in ("request", "care_plan", "appointments", "preferences", "feedback"):
        assert f"<{tag}>" in prompt and f"</{tag}>" in prompt
    assert "CP001-v2-02" in prompt and "slot_taken" in prompt
