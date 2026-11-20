import pytest

from careflow.agents.intake import IntakeRecord
from careflow.db.seed import PLANS
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


@pytest.mark.parametrize(
    "message",
    [
        "I can’t breathe properly",
        "I cant breathe",
        "I can't breath",
        "severe difficulty breathing",
        "short of breath at rest",
        "I blacked out",
        "my husband collapsed",
        "my chest hurts",
        "chest-pain since lunch",
        "chest   pain",
        "I want to end my life",
        "I don't want to live anymore",
        "I can not breathe",
        "I'm unable to breathe",
        "trouble breathing tonight",
        "it is hard to breathe",
        "pain in my chest",
        "my chest feels tight",
        "I do not want to live",
        "I wanna die",
        "My lips look blue",
        "his lips turned blue",
        "I could not breathe last night",
        "I keep passing out",
        "I feel faint",
        "I think it is a heart attack",
        "he has slurred speech since lunch",
        "I took an overdose",
        "I want to hurt myself",
        "I feel suicidal",
        "I have chest pains",
        "I had seizures this morning",
        "I overdosed on my pills",
        "my lips are bluish",
    ],
)
def test_red_flag_phrasings_escalate(message: str) -> None:
    assert evaluate_gate(message, None, []).level == EscalationLevel.EMERGENCY


@pytest.mark.parametrize(
    "description",
    [
        description
        for _, _, _, _, items in PLANS
        for kind, description, _, _, severity, rule in items
        if kind == "warning_sign" and severity == "emergency" and rule is None
    ],
)
def test_rule_less_emergency_signs_are_red_flags(description: str) -> None:
    assert evaluate_gate(description, None, []).level == EscalationLevel.EMERGENCY


def test_any_reading_over_the_limit_escalates() -> None:
    sign = {
        "id": "CP-fever",
        "severity": "urgent",
        "rule": {"measurement": "temperature_c", "op": ">", "value": 38.5},
    }
    readings = [{"name": "temperature_c", "value": 39.4}, {"name": "temperature_c", "value": 37.2}]
    item = {"kind": "symptom_report", "summary": "fever", "measurements": readings}
    intake = IntakeRecord.model_validate({"items": [item], "urgency": "routine"})
    assert evaluate_gate("fever", intake, [sign]).level == EscalationLevel.URGENT


@pytest.mark.parametrize(
    "message",
    [
        "I want to diet to lose some weight",
        "I feel confused about which appointment to book",
        "I'm confused about my tablets",
        "I had heatstroke years ago",
        "Can I book my blood test?",
    ],
)
def test_ordinary_messages_do_not_escalate(message: str) -> None:
    assert evaluate_gate(message, None, []).level == EscalationLevel.NONE
