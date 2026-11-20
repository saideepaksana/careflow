import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from careflow.api import app as app_module
from careflow.api.app import create_app
from careflow.api.deps import get_checkpointer
from careflow.config import NOTE_MAX_CHARS, Settings
from careflow.db import repository
from careflow.db.checkpointer import is_alive, open_checkpointer
from careflow.db.connection import connect
from careflow.graph.replies import EMERGENCY_REPLY
from careflow.graph.workflow import NoPendingInterrupt
from careflow.knowledge.rerank import FakeReranker
from careflow.memory.embeddings import FakeEmbedder
from tests.scripted import RoleLLM, book_lab, cited_answer, intake_reply, question

TOKEN = "coordinator-secret"
DIGEST = json.dumps({"episode": "Asked when the visit is.", "facts": []})
QUESTION_SCRIPT = {
    "intake": intake_reply([question("When is my cardiology visit?")]),
    "careplan": cited_answer("Your visit is on Wednesday."),
    "digest": DIGEST,
}


def make_client(url: str, script: dict[str, str], token: str = TOKEN) -> TestClient:
    app = create_app(RoleLLM(script))
    app.state.settings = Settings(database_url=url, coordinator_token=token)
    app.state.embedder = FakeEmbedder()
    app.state.reranker = FakeReranker()
    return TestClient(app)


@pytest.fixture
def client(fresh_db_url: str) -> TestClient:
    return make_client(fresh_db_url, QUESTION_SCRIPT)


def sign_in(client: TestClient, patient_id: str) -> dict:
    token = client.post("/api/login", json={"patient_id": patient_id}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def new_conversation(client: TestClient, headers: dict) -> str:
    return client.post("/api/conversations", headers=headers).json()["conversation_id"]


def test_unknown_patient_cannot_sign_in(client: TestClient) -> None:
    assert client.post("/api/login", json={"patient_id": "P999"}).status_code == 404


def test_posting_without_token_is_rejected(client: TestClient) -> None:
    response = client.post("/api/conversations/conv-x/messages", json={"text": "hi"})
    assert response.status_code == 401


def test_other_patients_conversation_is_hidden(client: TestClient) -> None:
    conversation_id = new_conversation(client, sign_in(client, "P001"))
    response = client.get(
        f"/api/conversations/{conversation_id}/messages", headers=sign_in(client, "P002")
    )
    assert response.status_code == 404


def test_message_gets_reply_and_is_stored(client: TestClient) -> None:
    headers = sign_in(client, "P001")
    conversation_id = new_conversation(client, headers)
    path = f"/api/conversations/{conversation_id}/messages"
    response = client.post(path, json={"text": "When is my visit?"}, headers=headers).json()
    stored = client.get(path, headers=headers).json()
    assert response["reply"].startswith("Your visit is on Wednesday. [")
    assert (response["status"], response["confirmation"]) == ("done", None)
    assert [(m["role"], m["content"]) for m in stored] == [
        ("patient", "When is my visit?"),
        ("assistant", response["reply"]),
    ]


def chat_once(client: TestClient) -> tuple[dict, str]:
    headers = sign_in(client, "P001")
    conversation_id = new_conversation(client, headers)
    path = f"/api/conversations/{conversation_id}/messages"
    client.post(path, json={"text": "When is my visit?"}, headers=headers)
    return headers, conversation_id


def test_ending_writes_an_episode(client: TestClient) -> None:
    headers, conversation_id = chat_once(client)
    response = client.post(f"/api/conversations/{conversation_id}/end", headers=headers)
    assert response.status_code == 200
    assert response.json()["episode_id"] > 0


@pytest.mark.parametrize(
    ("method", "suffix", "body"),
    [
        ("post", "end", None),
        ("post", "messages", {"text": "hello again"}),
        ("post", "confirm", {"approved": True}),
    ],
)
def test_ended_conversation_rejects_more(
    client: TestClient, method: str, suffix: str, body: dict | None
) -> None:
    headers, conversation_id = chat_once(client)
    client.post(f"/api/conversations/{conversation_id}/end", headers=headers)
    response = client.request(
        method, f"/api/conversations/{conversation_id}/{suffix}", json=body, headers=headers
    )
    assert response.status_code == 409


def start_booking(client: TestClient, text: str) -> tuple[dict, str, dict]:
    headers = sign_in(client, "P001")
    conversation_id = new_conversation(client, headers)
    path = f"/api/conversations/{conversation_id}/messages"
    reply = client.post(path, json={"text": text}, headers=headers).json()
    return headers, conversation_id, reply


def test_pending_confirmation_blocks_new_messages(fresh_db_url: str) -> None:
    client = make_client(fresh_db_url, book_lab("2026-11-03"))
    headers, conversation_id, reply = start_booking(client, "Book my blood test tomorrow")
    again = client.post(
        f"/api/conversations/{conversation_id}/messages", json={"text": "hi"}, headers=headers
    )
    assert reply["status"] == "awaiting_confirmation"
    assert reply["confirmation"].startswith("I can book your lab test for Tue 03 Nov")
    assert again.status_code == 409


def test_confirm_books_the_appointment(fresh_db_url: str) -> None:
    client = make_client(fresh_db_url, book_lab("2026-11-03"))
    headers, conversation_id, _ = start_booking(client, "Book my blood test tomorrow")
    path = f"/api/conversations/{conversation_id}/confirm"
    done = client.post(path, json={"approved": True}, headers=headers).json()
    again = client.post(path, json={"approved": True}, headers=headers)
    assert done["status"] == "done"
    assert done["reply"].startswith("Done.")
    assert again.status_code == 409


COORDINATOR_GETS = (
    "/api/coordinator/tasks",
    "/api/coordinator/patients",
    "/api/coordinator/patients/P001/timeline",
    "/api/coordinator/patients/P001/progress",
)


@pytest.mark.parametrize("path", COORDINATOR_GETS)
@pytest.mark.parametrize(
    ("token", "sent", "status"),
    [(TOKEN, "", 403), (TOKEN, "wrong", 403), ("", "", 403), (TOKEN, TOKEN, 200)],
)
def test_coordinator_endpoints_need_the_token(
    fresh_db_url: str, path: str, token: str, sent: str, status: int
) -> None:
    client = make_client(fresh_db_url, QUESTION_SCRIPT, token)
    response = client.get(path, headers={"X-Coordinator-Token": sent})
    assert response.status_code == status


def test_coordinator_decision_resumes_the_run(fresh_db_url: str) -> None:
    client = make_client(fresh_db_url, book_lab("2026-11-10"))
    headers, conversation_id, _ = start_booking(client, "Book my blood test on the 10th")
    client.post(
        f"/api/conversations/{conversation_id}/confirm", json={"approved": True}, headers=headers
    )
    coordinator = {"X-Coordinator-Token": TOKEN}
    [task] = client.get("/api/coordinator/tasks", headers=coordinator).json()
    path = f"/api/coordinator/tasks/{task['id']}/decision"
    decided = client.post(path, json={"approved": True, "note": "fine"}, headers=coordinator)
    repeat = client.post(path, json={"approved": True, "note": "fine"}, headers=coordinator)
    messages = client.get(f"/api/conversations/{conversation_id}/messages", headers=headers).json()
    assert task["kind"] == "approval"
    assert decided.json() == {"task_id": task["id"], "run_status": "done"}
    assert repeat.status_code == 409
    assert messages[-2]["content"].startswith("Done.")
    assert (messages[-1]["role"], messages[-1]["content"]) == ("coordinator", "fine")


COORDINATOR = {"X-Coordinator-Token": TOKEN}


def progress_of(client: TestClient, patient_id: str) -> dict[str, str]:
    rows = client.get(f"/api/coordinator/patients/{patient_id}/progress", headers=COORDINATOR)
    return {row["id"]: row["status"] for row in rows.json()}


def confirm(client: TestClient, headers: dict, conversation_id: str) -> dict:
    path = f"/api/conversations/{conversation_id}/confirm"
    return client.post(path, json={"approved": True}, headers=headers).json()


def test_confirm_stores_the_patient_answer(fresh_db_url: str) -> None:
    client = make_client(fresh_db_url, book_lab("2026-11-03"))
    headers, conversation_id, _ = start_booking(client, "Book my blood test tomorrow")
    confirm(client, headers, conversation_id)
    messages = client.get(f"/api/conversations/{conversation_id}/messages", headers=headers)
    assert [m["content"] for m in messages.json() if m["role"] == "patient"][-1] == "Yes"


def test_progress_moves_from_open_to_booked(fresh_db_url: str) -> None:
    client = make_client(fresh_db_url, book_lab("2026-11-03"))
    before = progress_of(client, "P001")["CP001-v2-02"]
    headers, conversation_id, _ = start_booking(client, "Book my blood test tomorrow")
    confirm(client, headers, conversation_id)
    assert (before, progress_of(client, "P001")["CP001-v2-02"]) == ("open", "booked")


def test_progress_marks_booking_after_due_date_late(fresh_db_url: str) -> None:
    client = make_client(fresh_db_url, book_lab("2026-11-10"))
    headers, conversation_id, _ = start_booking(client, "Book my blood test on the 10th")
    confirm(client, headers, conversation_id)
    [task] = client.get("/api/coordinator/tasks", headers=COORDINATOR).json()
    decision = {"approved": True, "note": ""}
    client.post(f"/api/coordinator/tasks/{task['id']}/decision", json=decision, headers=COORDINATOR)
    assert progress_of(client, "P001")["CP001-v2-02"] == "late"


def test_progress_marks_missed_item_overdue(
    fresh_db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = make_client(fresh_db_url, QUESTION_SCRIPT)
    monkeypatch.setenv("CAREFLOW_TODAY", "2026-11-30")
    assert progress_of(client, "P004") == {"CP004-v1-01": "booked", "CP004-v1-02": "overdue"}


def test_timeline_shows_message_task_and_booking(fresh_db_url: str) -> None:
    client = make_client(fresh_db_url, book_lab("2026-11-10"))
    headers, conversation_id, _ = start_booking(client, "Book my blood test on the 10th")
    confirm(client, headers, conversation_id)
    response = client.get("/api/coordinator/patients/P001/timeline", headers=COORDINATOR)
    kinds = {event["kind"] for event in response.json()}
    texts = [event["text"] for event in response.json()]
    assert {"message", "task_created"} <= kinds
    assert "Book my blood test on the 10th" in texts


def test_timeline_of_unknown_patient_is_404(fresh_db_url: str) -> None:
    client = make_client(fresh_db_url, QUESTION_SCRIPT)
    response = client.get("/api/coordinator/patients/P999/timeline", headers=COORDINATOR)
    assert response.status_code == 404


def test_timeline_and_queue_link_to_the_trace(fresh_db_url: str, spans) -> None:
    client = make_client(fresh_db_url, book_lab("2026-11-10"))
    headers, conversation_id, _ = start_booking(client, "Book my blood test on the 10th")
    confirm(client, headers, conversation_id)
    [task] = client.get("/api/coordinator/tasks", headers=COORDINATOR).json()
    events = client.get("/api/coordinator/patients/P001/timeline", headers=COORDINATOR).json()
    workflow = [event for event in events if event["kind"] == "workflow"]
    traces = {format(s.context.trace_id, "032x") for s in spans.get_finished_spans()}
    assert {event["text"] for event in workflow} == {
        "awaiting_confirmation",
        "awaiting_coordinator",
    }
    assert {event["detail"]["trace_id"] for event in workflow} <= traces
    assert task["trace_id"] in traces


def test_api_request_holds_one_trace(fresh_db_url: str, spans) -> None:
    client = make_client(fresh_db_url, QUESTION_SCRIPT)
    start_booking(client, "When is my visit?")
    finished = spans.get_finished_spans()
    by_name = {s.name: s for s in finished}
    root = by_name["POST /api/conversations/{conversation_id}/messages"]
    api, invocation = by_name["api.message"], by_name["careflow.invocation"]
    in_request = [s for s in finished if s.name.startswith(("api.", "careflow.", "workflow."))]
    assert root.parent is None
    assert invocation.parent.span_id == api.context.span_id
    assert {s.context.trace_id for s in in_request} == {root.context.trace_id}


@pytest.mark.parametrize("suffix", ["messages", "confirm", "end"])
def test_busy_conversation_is_refused(fresh_db_url: str, suffix: str) -> None:
    client = make_client(fresh_db_url, QUESTION_SCRIPT)
    headers = sign_in(client, "P001")
    conversation_id = new_conversation(client, headers)
    body = {"messages": {"text": "hi"}, "confirm": {"approved": True}, "end": None}[suffix]
    with connect(fresh_db_url, autocommit=True) as other:
        with repository.conversation_lock(other, conversation_id) as locked:
            response = client.post(
                f"/api/conversations/{conversation_id}/{suffix}", json=body, headers=headers
            )
    assert locked
    assert response.status_code == 423
    assert response.json()["detail"] == "still working on the previous request"


def test_lock_is_released_after_a_request(client: TestClient) -> None:
    headers, conversation_id = chat_once(client)
    path = f"/api/conversations/{conversation_id}/messages"
    assert client.post(path, json={"text": "and again"}, headers=headers).status_code == 200


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/api/login", '{"patient_id": "P001\\u0000"}'),
        ("/api/login", '{"patient_id": "\\ud800"}'),
        ("messages", '{"text": "hi\\u0000there"}'),
        ("messages", '{"text": "broken \\ud800 text"}'),
    ],
)
def test_unstorable_text_is_bad_input(client: TestClient, path: str, body: str) -> None:
    headers = {**sign_in(client, "P001"), "Content-Type": "application/json"}
    if path == "messages":
        path = f"/api/conversations/{new_conversation(client, headers)}/messages"
    assert client.post(path, content=body, headers=headers).status_code == 422


def test_non_ascii_coordinator_token_is_forbidden(client: TestClient) -> None:
    sent = "café".encode("latin-1")
    response = client.get("/api/coordinator/tasks", headers={"X-Coordinator-Token": sent})
    assert response.status_code == 403


def test_confirm_without_a_live_interrupt_is_a_conflict(
    fresh_db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_interrupt(*_: object) -> None:
        raise NoPendingInterrupt("gone")

    client = make_client(fresh_db_url, book_lab("2026-11-03"))
    headers, conversation_id, _ = start_booking(client, "Book my blood test tomorrow")
    monkeypatch.setattr(app_module, "resume_run", no_interrupt)
    path = f"/api/conversations/{conversation_id}/confirm"
    response = client.post(path, json={"approved": True}, headers=headers)
    assert response.status_code == 409


def test_broken_checkpointer_connection_is_reopened(fresh_db_url: str) -> None:
    app = make_client(fresh_db_url, QUESTION_SCRIPT).app
    request = SimpleNamespace(app=app)
    first = get_checkpointer(request)
    first.conn.close()
    second = get_checkpointer(request)
    assert second is not first
    assert not second.conn.closed
    second.conn.close()


@pytest.mark.parametrize(
    "path",
    [
        "/api/conversations/a%00b/messages",
        "/api/coordinator/patients/P%00/timeline",
        "/api/coordinator/patients/P%00/progress",
    ],
)
def test_unstorable_path_ids_are_rejected(client: TestClient, path: str) -> None:
    headers = {**sign_in(client, "P001"), **COORDINATOR}
    assert client.get(path, headers=headers).status_code == 422


def test_overlong_coordinator_note_is_rejected(client: TestClient) -> None:
    path = "/api/coordinator/tasks/1/decision"
    body = {"approved": True, "note": "x" * (NOTE_MAX_CHARS + 1)}
    assert client.post(path, json=body, headers=COORDINATOR).status_code == 422


def test_approval_for_a_run_in_flight_is_refused(fresh_db_url: str) -> None:
    client = make_client(fresh_db_url, book_lab("2026-11-10"))
    headers, conversation_id, _ = start_booking(client, "Book my blood test on the 10th")
    client.post(
        f"/api/conversations/{conversation_id}/confirm", json={"approved": True}, headers=headers
    )
    [task] = client.get("/api/coordinator/tasks", headers=COORDINATOR).json()
    with connect(fresh_db_url, autocommit=True) as conn:
        repository.set_run_status(conn, task["thread_id"], "running")
    path = f"/api/coordinator/tasks/{task['id']}/decision"
    response = client.post(path, json={"approved": True, "note": ""}, headers=COORDINATOR)
    assert response.status_code == 409
    assert client.get("/api/coordinator/tasks", headers=COORDINATOR).json()[0]["id"] == task["id"]


def test_checkpointer_killed_by_the_server_is_detected(fresh_db_url: str) -> None:
    saver = open_checkpointer(fresh_db_url)
    with connect(fresh_db_url, autocommit=True) as admin:
        admin.execute("SELECT pg_terminate_backend(%s)", (saver.conn.info.backend_pid,))
    assert not is_alive(saver)


def test_red_flag_during_pending_confirmation_escalates(fresh_db_url: str) -> None:
    client = make_client(fresh_db_url, book_lab("2026-11-03"))
    headers, conversation_id, waiting = start_booking(client, "Book my blood test tomorrow")
    path = f"/api/conversations/{conversation_id}/messages"
    reply = client.post(path, json={"text": "I have chest pain right now"}, headers=headers)
    tasks = client.get("/api/coordinator/tasks", headers=COORDINATOR).json()
    with connect(fresh_db_url, autocommit=True) as conn:
        lab_bookings = conn.execute(
            "SELECT count(*) AS n FROM appointments WHERE care_plan_item_id = 'CP001-v2-02'"
        ).fetchone()["n"]
        pending = repository.pending_confirmation(conn, conversation_id)
    assert waiting["status"] == "awaiting_confirmation"
    assert reply.status_code == 200
    assert reply.json()["reply"].startswith(EMERGENCY_REPLY)
    assert [(t["kind"], t["priority"]) for t in tasks] == [("escalation", "emergency")]
    assert pending is None
    assert lab_bookings == 0
