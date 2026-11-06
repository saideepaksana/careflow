from careflow.agents.intake import IntakeItem, IntakeRecord, ItemKind, Urgency
from careflow.evaluation.intake_eval import IntakeCase, load_cases, score


def make_case(case_id: str, urgency: Urgency) -> IntakeCase:
    return IntakeCase(
        id=case_id, message="m", urgency=urgency, kinds=[ItemKind.symptom_report], injection=False
    )


def make_record(urgency: Urgency) -> IntakeRecord:
    item = IntakeItem(kind=ItemKind.symptom_report, summary="s")
    return IntakeRecord(items=[item], urgency=urgency)


def test_all_correct_scores_one() -> None:
    cases = [make_case("a", Urgency.emergency), make_case("b", Urgency.routine)]
    scores = score(cases, [make_record(Urgency.emergency), make_record(Urgency.routine)])
    assert scores.urgency_accuracy == 1.0
    assert scores.kinds_accuracy == 1.0
    assert scores.emergency_recall == 1.0


def test_missed_emergency_is_reported() -> None:
    scores = score([make_case("a", Urgency.emergency)], [make_record(Urgency.urgent)])
    assert scores.emergency_recall == 0.0
    assert scores.missed_emergency_ids == ["a"]


def test_failed_record_is_wrong_but_not_a_missed_emergency() -> None:
    scores = score([make_case("a", Urgency.emergency)], [None])
    assert scores.valid_rate == 0.0
    assert scores.urgency_accuracy == 0.0
    assert scores.emergency_recall == 1.0


def test_labelled_set_loads() -> None:
    assert len(load_cases()) == 30
