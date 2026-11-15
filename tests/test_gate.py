import pytest

from careflow.agents.intake import IntakeRecord
from careflow.safety.gate import EscalationLevel, evaluate_gate

WEIGHT_SIGN = {
    "id": "CP001-v2-04",
    "severity": "urgent",
    "rule": {"measurement": "weight_change_kg", "op": ">", "value": 2},
}
CHEST_SIGN = {"id": "CP001-v2-05", "severity": "emergency", "rule": None}


def record(urgency: str = "routine", weight: float | None = None) -> IntakeRecord:
    measurements = [{"name": "weight_change_kg", "value": weight}] if weight is not None else []
    item = {"kind": "symptom_report", "summary": "update", "measurements": measurements}
    return IntakeRecord.model_validate({"items": [item], "urgency": urgency})


@pytest.mark.parametrize(
    ("message", "intake", "signs", "level"),
    [
        ("I have chest pain since morning", record(), [], EscalationLevel.EMERGENCY),
        ("I gained some weight", record(weight=2.5), [WEIGHT_SIGN], EscalationLevel.URGENT),
        ("I gained some weight", record(weight=2.5), [], EscalationLevel.NONE),
        ("I gained some weight", record(weight=1.5), [WEIGHT_SIGN], EscalationLevel.NONE),
        ("my ankles are swollen", record("urgent"), [], EscalationLevel.URGENT),
        ("I'm confused about my tablets", record(), [], EscalationLevel.NONE),
        ("I fainted this morning", None, [], EscalationLevel.EMERGENCY),
        ("Can I book a visit?", None, [CHEST_SIGN], EscalationLevel.NONE),
    ],
)
def test_gate_level(
    message: str, intake: IntakeRecord | None, signs: list[dict], level: EscalationLevel
) -> None:
    assert evaluate_gate(message, intake, signs).level == level


def test_warning_sign_reason_is_recorded() -> None:
    decision = evaluate_gate("weight up", record(weight=2.5), [WEIGHT_SIGN])
    assert decision.reasons == ["warning_sign:CP001-v2-04"]


def test_highest_rule_wins_over_lower_intake_urgency() -> None:
    decision = evaluate_gate("chest pain and weight up", record("urgent", 2.5), [WEIGHT_SIGN])
    assert decision.level == EscalationLevel.EMERGENCY
    assert set(decision.reasons) == {
        "red_flag:chest pain",
        "warning_sign:CP001-v2-04",
        "intake:urgent",
    }
