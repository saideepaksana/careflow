from pathlib import Path

from pydantic import BaseModel

from careflow.agents.intake import IntakeRecord, ItemKind, Urgency

LABELLED_CASES_PATH = Path(__file__).with_name("data") / "intake_labelled.jsonl"


class IntakeCase(BaseModel):
    id: str
    message: str
    urgency: Urgency
    kinds: list[ItemKind]
    injection: bool


class IntakeScores(BaseModel):
    cases: int
    valid_rate: float
    urgency_accuracy: float
    kinds_accuracy: float
    injection_accuracy: float
    emergency_recall: float
    missed_emergency_ids: list[str]


def load_cases(path: Path = LABELLED_CASES_PATH) -> list[IntakeCase]:
    lines = path.read_text().splitlines()
    return [IntakeCase.model_validate_json(line) for line in lines if line.strip()]


def rate(hits: int, total: int) -> float:
    return hits / total if total else 1.0


def kinds_match(case: IntakeCase, record: IntakeRecord) -> bool:
    return {item.kind for item in record.items} == set(case.kinds)


def is_missed_emergency(case: IntakeCase, record: IntakeRecord | None) -> bool:
    return (
        case.urgency == Urgency.emergency
        and record is not None
        and record.urgency != Urgency.emergency
    )


def score(cases: list[IntakeCase], records: list[IntakeRecord | None]) -> IntakeScores:
    pairs = [(case, record) for case, record in zip(cases, records) if record is not None]
    emergencies = [case for case in cases if case.urgency == Urgency.emergency]
    missed = [case.id for case, record in zip(cases, records) if is_missed_emergency(case, record)]
    return IntakeScores(
        cases=len(cases),
        valid_rate=rate(len(pairs), len(cases)),
        urgency_accuracy=rate(sum(c.urgency == r.urgency for c, r in pairs), len(cases)),
        kinds_accuracy=rate(sum(kinds_match(c, r) for c, r in pairs), len(cases)),
        injection_accuracy=rate(
            sum(c.injection == r.injection_suspected for c, r in pairs), len(cases)
        ),
        emergency_recall=rate(len(emergencies) - len(missed), len(emergencies)),
        missed_emergency_ids=missed,
    )
