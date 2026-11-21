import psycopg
import pytest
from langgraph.checkpoint.memory import InMemorySaver

from careflow.db import repository
from careflow.graph import nodes, replies
from careflow.graph.nodes import WorkflowDeps
from careflow.graph.replies import HANDOFF_REPLY
from careflow.graph.workflow import (
    NoPendingInterrupt,
    RunContext,
    RunResult,
    resume_run,
    start_run,
)
from careflow.knowledge.rerank import FakeReranker
from careflow.memory.embeddings import FakeEmbedder
from careflow.observability.budget import RequestBudget, request_budget
from tests.scripted import (
    RoleLLM,
    appointment,
    book_lab,
    cited_answer,
    intake_reply,
    planner_reply,
    question,
)

CONVERSATION = "conv-flow"


class Flow:
    def __init__(self, conn: psycopg.Connection, replies_by_role: dict[str, str]) -> None:
        self.conn = conn
        self.llm = RoleLLM(replies_by_role)
        self.deps = WorkflowDeps(conn, self.llm, FakeEmbedder(), FakeReranker())
        self.saver = InMemorySaver()

    def start(self, message: str, patient_id: str = "P001") -> RunResult:
        repository.create_conversation(self.conn, f"{CONVERSATION}-{patient_id}", patient_id)
        return start_run(
            self.deps, self.saver, f"{CONVERSATION}-{patient_id}", patient_id, message, RunContext()
        )

    def resume(self, result: RunResult, kind: str, value: object) -> RunResult:
        return resume_run(self.deps, self.saver, result.thread_id, kind, value)


def count(conn: psycopg.Connection, sql: str) -> int:
    return conn.execute(sql).fetchone()["n"]


def tasks(conn: psycopg.Connection) -> list[dict]:
    return conn.execute(
        "SELECT kind, priority, status, detail->>'text' AS text FROM coordinator_tasks ORDER BY id"
    ).fetchall()


def lab_bookings(conn: psycopg.Connection) -> int:
    return count(
        conn,
        "SELECT count(*) AS n FROM appointments"
        " WHERE care_plan_item_id = 'CP001-v2-02' AND status = 'booked'",
    )


def test_care_plan_question_gets_cited_reply(workflow_conn: psycopg.Connection) -> None:
    flow = Flow(
        workflow_conn,
        {
            "intake": intake_reply([question("How much fluid can I drink a day?")]),
            "careplan": cited_answer("Drink at most 1.5 litres a day."),
        },
    )
    result = flow.start("How much can I drink?")
    assert result.status == "done"
    assert result.messages[0].startswith("Drink at most 1.5 litres a day. [")
    assert tasks(workflow_conn) == []


def test_running_example_escalates_and_does_not_reschedule(
    workflow_conn: psycopg.Connection,
) -> None:
    symptom = {
        "kind": "symptom_report",
        "summary": "Weight gain of 2.5 kg",
        "measurements": [{"name": "weight_change_kg", "value": 2.5}],
    }
    items = [appointment("reschedule", "Move cardiology to next Wednesday"), symptom]
    flow = Flow(workflow_conn, {"intake": intake_reply(items)})
    result = flow.start("Move my cardiology visit to Wednesday. I put on 2.5 kg since Sunday.")
    [task] = tasks(workflow_conn)
    appointment_row = repository.get_appointment(workflow_conn, "P001", "A001")
    assert result.messages == [f"{replies.URGENT_REPLY} {replies.HELD_CHANGE_REPLY}"]
    assert (task["kind"], task["priority"]) == ("escalation", "urgent")
    assert "Move cardiology to next Wednesday" in task["text"]
    assert "warning sign: Weight gain over 2 kg in a week" in task["text"]
    assert appointment_row["slot_id"] == "S-C01-20261111-1000"
    assert "planner" not in flow.llm.calls


def test_red_flag_overrides_routine_intake(workflow_conn: psycopg.Connection) -> None:
    flow = Flow(workflow_conn, {"intake": intake_reply([question("Is this normal?")])})
    result = flow.start("I have chest pain, is this normal?")
    assert result.messages == [replies.EMERGENCY_REPLY]
    assert [(t["kind"], t["priority"]) for t in tasks(workflow_conn)] == [
        ("escalation", "emergency")
    ]
    assert 'red-flag phrase "chest pain"' in tasks(workflow_conn)[0]["text"]


@pytest.mark.parametrize(("answer", "booked"), [(True, 1), (False, 0)])
def test_in_plan_booking_needs_patient_confirmation(
    workflow_conn: psycopg.Connection, answer: bool, booked: int
) -> None:
    flow = Flow(workflow_conn, book_lab("2026-11-03"))
    waiting = flow.start("Book my blood test for tomorrow morning")
    done = flow.resume(waiting, "confirmation", answer)
    assert (waiting.status, waiting.confirmation is not None) == ("awaiting_confirmation", True)
    assert lab_bookings(workflow_conn) == booked
    assert done.status == "done"


def test_reschedule_inside_due_date(workflow_conn: psycopg.Connection) -> None:
    flow = Flow(
        workflow_conn,
        {
            "intake": intake_reply([appointment("reschedule", "Move cardiology earlier")]),
            "planner": planner_reply("reschedule", "2026-11-05", appointment_id="A001"),
        },
    )
    waiting = flow.start("Can I move my cardiology visit to Thursday?")
    flow.resume(waiting, "confirmation", True)
    booked = repository.list_appointments(workflow_conn, "P001")
    cardiology = [row for row in booked if row["care_plan_item_id"] == "CP001-v2-01"]
    assert [row["slot_id"] for row in cardiology] == ["S-C01-20261105-0900"]


@pytest.mark.parametrize(("approved", "booked"), [(True, 1), (False, 0)])
def test_booking_past_due_date_waits_for_coordinator(
    workflow_conn: psycopg.Connection, approved: bool, booked: int
) -> None:
    flow = Flow(workflow_conn, book_lab("2026-11-10"))
    waiting = flow.start("Book my blood test for the 10th")
    pending = flow.resume(waiting, "confirmation", True)
    done = flow.resume(pending, "coordinator", {"approved": approved, "note": "ok"})
    assert pending.status == "awaiting_coordinator"
    assert pending.messages == [replies.APPROVAL_PENDING_REPLY]
    assert [(t["kind"], t["status"]) for t in tasks(workflow_conn)] == [("approval", "resolved")]
    assert lab_bookings(workflow_conn) == booked
    assert done.status == "done"


def test_budget_hand_off_does_not_reuse_the_current_item_key() -> None:
    state = {"pending": [1], "current": 0, "outcome": [], "thread_id": "t"}
    with request_budget(RequestBudget(max_seconds=0)):
        stop = nodes.capped(state, 1)
    assert stop["route"] == "hand_off"
    assert nodes.task_key({**state, **stop}, "hand_off") != nodes.task_key(state, "hand_off")


def test_replans_are_capped_then_handed_off(workflow_conn: psycopg.Connection) -> None:
    flow = Flow(
        workflow_conn,
        {
            "intake": intake_reply([appointment("book", "Book a visit")]),
            "planner": planner_reply("book", "2026-11-03", care_plan_item_id="CP999"),
        },
    )
    result = flow.start("Book my visit")
    assert flow.llm.calls.count("planner") == nodes.MAX_REPLANS + 1
    assert result.messages == [HANDOFF_REPLY]
    assert [t["kind"] for t in tasks(workflow_conn)] == ["handoff"]


def test_two_hand_offs_reply_once(workflow_conn: psycopg.Connection) -> None:
    items = [
        {"kind": "clinical_request", "summary": "Wants to stop furosemide"},
        {"kind": "symptom_report", "summary": "Passing urine often"},
    ]
    result = Flow(workflow_conn, {"intake": intake_reply(items)}).start("Can I stop furosemide?")
    assert result.messages == [HANDOFF_REPLY]
    assert [t["kind"] for t in tasks(workflow_conn)] == ["handoff", "handoff"]


@pytest.mark.parametrize("role", ["intake", "planner"])
def test_llm_failure_hands_off(workflow_conn: psycopg.Connection, role: str) -> None:
    script = {**book_lab("2026-11-03"), role: "not json"}
    result = Flow(workflow_conn, script).start("Book my blood test")
    assert result.messages == [HANDOFF_REPLY]
    assert [t["kind"] for t in tasks(workflow_conn)] == ["handoff"]


def test_resuming_wrong_kind_is_refused(workflow_conn: psycopg.Connection) -> None:
    flow = Flow(workflow_conn, book_lab("2026-11-03"))
    waiting = flow.start("Book my blood test for tomorrow")
    with pytest.raises(NoPendingInterrupt):
        flow.resume(waiting, "coordinator", {"approved": True})


def test_supervisor_steps_are_capped(
    workflow_conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(nodes, "SUPERVISOR_MAX_STEPS", 1)
    items = [question("First question"), question("Second question")]
    flow = Flow(workflow_conn, {"intake": intake_reply(items), "careplan": cited_answer("Yes.")})
    flow.start("Two questions")
    detail = workflow_conn.execute(
        "SELECT detail FROM audit_events WHERE event = 'workflow_finished'"
    ).fetchone()["detail"]
    assert detail["outcome"][-1] == "cap:1"
    assert flow.llm.calls.count("careplan") == 1


def test_part_of_day_picks_a_matching_slot(workflow_conn: psycopg.Connection) -> None:
    script = book_lab("2026-11-03")
    script["planner"] = planner_reply(
        "book", "2026-11-03", care_plan_item_id="CP001-v2-02", part_of_day="afternoon"
    )
    waiting = Flow(workflow_conn, script).start("Book my blood test tomorrow afternoon")
    assert "at 14:00" in waiting.confirmation


def test_spent_budget_hands_off_before_planning(workflow_conn: psycopg.Connection) -> None:
    flow = Flow(workflow_conn, book_lab("2026-11-03"))
    with request_budget(RequestBudget(max_seconds=0)):
        result = flow.start("Book my blood test")
    [task] = tasks(workflow_conn)
    assert "planner" not in flow.llm.calls
    assert result.messages == [HANDOFF_REPLY]
    assert "reason: budget" in task["text"]


@pytest.mark.parametrize(
    ("message", "kind", "priority"),
    [
        ("I fainted this morning", "escalation", "emergency"),
        ("I have put on 2.5 kg since Sunday", "handoff", "urgent"),
    ],
)
def test_intake_failure_still_errs_towards_escalation(
    workflow_conn: psycopg.Connection, message: str, kind: str, priority: str
) -> None:
    Flow(workflow_conn, {"intake": "not json"}).start(message)
    assert [(t["kind"], t["priority"]) for t in tasks(workflow_conn)] == [(kind, priority)]


def test_intake_failure_under_spent_budget_stays_urgent(workflow_conn: psycopg.Connection) -> None:
    flow = Flow(workflow_conn, {"intake": "not json"})
    with request_budget(RequestBudget(max_seconds=0)):
        flow.start("My chest feels odd")
    assert [(t["kind"], t["priority"]) for t in tasks(workflow_conn)] == [("handoff", "urgent")]
