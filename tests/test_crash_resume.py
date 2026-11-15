from collections.abc import Callable

import psycopg
import pytest

from careflow.db import repository
from careflow.db.checkpointer import open_checkpointer
from careflow.graph.nodes import WorkflowDeps
from careflow.graph.workflow import Crash, RunContext, RunResult, recover_run, resume_run, start_run
from careflow.knowledge.rerank import FakeReranker
from careflow.memory.embeddings import FakeEmbedder
from tests.scripted import RoleLLM, book_lab

CONVERSATION = "conv-crash"
BOOKING_NODES = (
    "intake",
    "safety_gate",
    "supervisor",
    "plan_schedule",
    "verify",
    "ask_confirmation",
    "execute",
    "finalize",
)
APPROVE = {"approved": True, "note": ""}
PATHS = {
    "booking": {
        "day": "2026-11-03",
        "resumes": [("confirmation", True)],
        "nodes": BOOKING_NODES,
        "slot": "S-C08-20261103-0900",
        "tasks": [],
        "messages": 2,
    },
    "approval": {
        "day": "2026-11-10",
        "resumes": [("confirmation", True), ("coordinator", APPROVE)],
        "nodes": (*BOOKING_NODES, "await_coordinator"),
        "slot": "S-C08-20261110-0900",
        "tasks": [{"kind": "approval", "status": "resolved"}],
        "messages": 3,
    },
}
CASES = [
    (path, f"{phase}:{node}")
    for path, spec in PATHS.items()
    for node in spec["nodes"]
    for phase in ("before", "after")
]


class SimulatedCrash(Exception):
    pass


def crash_once(point: str, fired: list[str]) -> Crash:
    def crash(current: str) -> None:
        if current == point and not fired:
            fired.append(current)
            raise SimulatedCrash(current)

    return crash


def survive(deps: WorkflowDeps, url: str, step: Callable[[], RunResult]) -> RunResult:
    try:
        return step()
    except SimulatedCrash:
        [thread_id] = repository.runs_with_status(deps.conn, "running")
        return recover_run(deps, open_checkpointer(url), thread_id)


def drive(conn: psycopg.Connection, url: str, path: str, point: str, fired: list[str]) -> RunResult:
    spec = PATHS[path]
    repository.create_conversation(conn, CONVERSATION, "P001")
    deps = WorkflowDeps(conn, RoleLLM(book_lab(spec["day"])), FakeEmbedder(), FakeReranker())
    crash = crash_once(point, fired)
    result = survive(
        deps,
        url,
        lambda: start_run(
            deps, open_checkpointer(url), CONVERSATION, "P001", "Book it", RunContext(), crash
        ),
    )
    for kind, value in spec["resumes"]:
        thread_id = result.thread_id
        result = survive(
            deps,
            url,
            lambda: resume_run(deps, open_checkpointer(url), thread_id, kind, value, crash),
        )
    return result


@pytest.mark.parametrize(("path", "point"), CASES)
def test_crash_at_any_node_resumes_to_same_state(
    workflow_conn: psycopg.Connection, fresh_db_url: str, path: str, point: str
) -> None:
    spec = PATHS[path]
    fired: list[str] = []
    result = drive(workflow_conn, fresh_db_url, path, point, fired)
    lab = workflow_conn.execute(
        "SELECT slot_id FROM appointments WHERE care_plan_item_id = 'CP001-v2-02'"
    ).fetchall()
    tasks = workflow_conn.execute("SELECT kind, status FROM coordinator_tasks").fetchall()
    messages = [
        row["content"]
        for row in workflow_conn.execute(
            "SELECT content FROM messages WHERE role = 'assistant'"
        ).fetchall()
    ]
    assert fired == [point]
    assert result.status == "done"
    assert [row["slot_id"] for row in lab] == [spec["slot"]]
    assert tasks == spec["tasks"]
    assert len(messages) == spec["messages"] == len(set(messages))
