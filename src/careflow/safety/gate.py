import operator
from enum import StrEnum

from pydantic import BaseModel

from careflow.agents.intake import IntakeRecord, Urgency
from careflow.config import RED_FLAG_TERMS

COMPARISONS = {">": operator.gt, ">=": operator.ge, "<": operator.lt, "<=": operator.le}


class EscalationLevel(StrEnum):
    EMERGENCY = "emergency"
    URGENT = "urgent"
    NONE = "none"


SEVERITY_ORDER = (EscalationLevel.NONE, EscalationLevel.URGENT, EscalationLevel.EMERGENCY)


class GateDecision(BaseModel):
    level: EscalationLevel
    reasons: list[str]


def red_flag_reasons(message: str) -> list[tuple[EscalationLevel, str]]:
    text = message.lower()
    return [
        (EscalationLevel.EMERGENCY, f"red_flag:{term}") for term in RED_FLAG_TERMS if term in text
    ]


def sign_matches(rule: dict, measurements: dict[str, float]) -> bool:
    compare = COMPARISONS.get(rule.get("op", ""))
    value = measurements.get(rule.get("measurement", ""))
    return compare is not None and value is not None and compare(value, rule["value"])


def warning_sign_reasons(
    intake: IntakeRecord | None, warning_signs: list[dict]
) -> list[tuple[EscalationLevel, str]]:
    if intake is None:
        return []
    measurements = {m.name.value: m.value for item in intake.items for m in item.measurements}
    return [
        (EscalationLevel(sign["severity"]), f"warning_sign:{sign['id']}")
        for sign in warning_signs
        if sign.get("rule") and sign_matches(sign["rule"], measurements)
    ]


def intake_reasons(intake: IntakeRecord | None) -> list[tuple[EscalationLevel, str]]:
    if intake is None or intake.urgency == Urgency.routine:
        return []
    return [(EscalationLevel(intake.urgency.value), f"intake:{intake.urgency.value}")]


def evaluate_gate(
    message: str, intake: IntakeRecord | None, warning_signs: list[dict]
) -> GateDecision:
    """Escalation floor: the highest level any rule reaches; nothing can lower it."""
    findings = (
        red_flag_reasons(message)
        + warning_sign_reasons(intake, warning_signs)
        + intake_reasons(intake)
    )
    level = max(
        (level for level, _ in findings), key=SEVERITY_ORDER.index, default=EscalationLevel.NONE
    )
    return GateDecision(level=level, reasons=[reason for _, reason in findings])
