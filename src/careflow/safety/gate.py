import operator
import re
from enum import StrEnum

from pydantic import BaseModel

from careflow.agents.intake import IntakeRecord, Urgency
from careflow.config import RED_FLAG_TERMS

COMPARISONS = {">": operator.gt, ">=": operator.ge, "<": operator.lt, "<=": operator.le}
APOSTROPHES = re.compile(r"['\u2018\u2019`]")
SEPARATORS = re.compile(r"[\s\-\u2010-\u2015]+")
CONTRACTIONS = (
    ("can not", "cant"),
    ("cannot", "cant"),
    ("could not", "couldnt"),
    ("do not", "dont"),
    ("wanna", "want to"),
)
RED_FLAG_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(term) for term in RED_FLAG_TERMS) + r")(?:s|es)?\b"
)


class EscalationLevel(StrEnum):
    EMERGENCY = "emergency"
    URGENT = "urgent"
    NONE = "none"


SEVERITY_ORDER = (EscalationLevel.NONE, EscalationLevel.URGENT, EscalationLevel.EMERGENCY)


class GateDecision(BaseModel):
    level: EscalationLevel
    reasons: list[str]


def normalize(text: str) -> str:
    text = SEPARATORS.sub(" ", APOSTROPHES.sub("", text.lower())).strip()
    for phrase, contraction in CONTRACTIONS:
        text = text.replace(phrase, contraction)
    return text


def red_flag_reasons(message: str) -> list[tuple[EscalationLevel, str]]:
    terms = dict.fromkeys(RED_FLAG_PATTERN.findall(normalize(message)))
    return [(EscalationLevel.EMERGENCY, f"red_flag:{term}") for term in terms]


def sign_matches(rule: dict, measurements: dict[str, list[float]]) -> bool:
    compare = COMPARISONS.get(rule.get("op", ""))
    values = measurements.get(rule.get("measurement", ""), [])
    return compare is not None and any(compare(value, rule["value"]) for value in values)


def collect_measurements(intake: IntakeRecord) -> dict[str, list[float]]:
    measurements: dict[str, list[float]] = {}
    for item in intake.items:
        for measurement in item.measurements:
            measurements.setdefault(measurement.name.value, []).append(measurement.value)
    return measurements


def warning_sign_reasons(
    intake: IntakeRecord | None, warning_signs: list[dict]
) -> list[tuple[EscalationLevel, str]]:
    if intake is None:
        return []
    measurements = collect_measurements(intake)
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
