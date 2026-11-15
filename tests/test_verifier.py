import psycopg
import pytest

from careflow.agents.scheduler import SchedulingPlan
from careflow.db import repository
from careflow.safety.verifier import VerdictKind, verify_plan

LAB_ITEM = "CP001-v2-02"
CARDIOLOGY_ITEM = "CP001-v2-01"


def plan(action: str = "book", **fields: str) -> SchedulingPlan:
    return SchedulingPlan(action=action, **fields)


@pytest.mark.parametrize(
    ("candidate", "kind", "reason", "fixable"),
    [
        (
            plan(care_plan_item_id=LAB_ITEM, slot_id="S-C08-20261103-0900"),
            VerdictKind.APPROVED,
            "in_plan",
            False,
        ),
        (
            plan(care_plan_item_id=LAB_ITEM, slot_id="S-C08-20261110-0900"),
            VerdictKind.NEEDS_APPROVAL,
            "past_due_date",
            False,
        ),
        (
            plan(care_plan_item_id="CP002-v1-01", slot_id="S-C08-20261103-0900"),
            VerdictKind.REJECTED,
            "item_not_in_plan",
            True,
        ),
        (
            plan(care_plan_item_id=LAB_ITEM, slot_id="S-C01-20261103-0900"),
            VerdictKind.REJECTED,
            "specialty_mismatch",
            True,
        ),
        (
            plan(care_plan_item_id=LAB_ITEM, slot_id="S-C01-20261111-1000"),
            VerdictKind.REJECTED,
            "slot_taken",
            True,
        ),
        (plan(care_plan_item_id=LAB_ITEM), VerdictKind.REJECTED, "no_free_slot", False),
        (
            plan(care_plan_item_id=CARDIOLOGY_ITEM, slot_id="S-C01-20261104-0900"),
            VerdictKind.REJECTED,
            "already_booked",
            False,
        ),
        (
            plan(specialty="pulmonology", slot_id="S-C03-20261104-0900"),
            VerdictKind.NEEDS_APPROVAL,
            "not_in_plan",
            False,
        ),
        (
            plan("reschedule", appointment_id="A001", slot_id="S-C01-20261104-0900"),
            VerdictKind.APPROVED,
            "in_plan",
            False,
        ),
        (
            plan("reschedule", appointment_id="A002", slot_id="S-C05-20261104-0900"),
            VerdictKind.REJECTED,
            "appointment_not_found",
            True,
        ),
        (
            plan("cancel", appointment_id="A001"),
            VerdictKind.NEEDS_APPROVAL,
            "cancels_plan_item",
            False,
        ),
    ],
)
def test_verdicts(
    db: psycopg.Connection, candidate: SchedulingPlan, kind: VerdictKind, reason: str, fixable: bool
) -> None:
    verdict = verify_plan(db, "P001", candidate)
    assert (verdict.kind, verdict.reason, verdict.fixable) == (kind, reason, fixable)


def test_cancel_outside_plan_is_approved(db: psycopg.Connection) -> None:
    booked = repository.book_appointment(db, "P001", "S-C03-20261104-0900", None, "test-key")
    verdict = verify_plan(db, "P001", plan("cancel", appointment_id=booked["appointment_id"]))
    assert verdict.kind == VerdictKind.APPROVED
