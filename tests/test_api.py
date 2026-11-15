import json

import pytest
from fastapi.testclient import TestClient

from careflow.api.app import create_app
from careflow.config import Settings
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
    [("post", "end", None), ("post", "messages", {"text": "hello again"})],
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
    assert reply["confirmation"].startswith("I can book laboratory")
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


@pytest.mark.parametrize(
    ("token", "sent", "status"),
    [(TOKEN, "", 403), (TOKEN, "wrong", 403), ("", "", 403), (TOKEN, TOKEN, 200)],
)
def test_coordinator_endpoints_need_the_token(
    fresh_db_url: str, token: str, sent: str, status: int
) -> None:
    client = make_client(fresh_db_url, QUESTION_SCRIPT, token)
    response = client.get("/api/coordinator/tasks", headers={"X-Coordinator-Token": sent})
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
    assert messages[-1]["content"].startswith("Done.")
