import json

import pytest
from fastapi.testclient import TestClient

from careflow.api.app import create_app
from careflow.config import Settings
from careflow.llm.gateway import FakeLLM


@pytest.fixture
def client(seeded_db_url: str) -> TestClient:
    llm = FakeLLM([json.dumps({"action": "reply", "reply": "Your visit is on Wednesday."})])
    app = create_app(llm)
    app.state.settings = Settings(database_url=seeded_db_url)
    return TestClient(app)


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
    response = client.post(path, json={"text": "When is my visit?"}, headers=headers)
    stored = client.get(path, headers=headers).json()
    assert response.json() == {"reply": "Your visit is on Wednesday.", "stop_reason": "replied"}
    assert [(m["role"], m["content"]) for m in stored] == [
        ("patient", "When is my visit?"),
        ("assistant", "Your visit is on Wednesday."),
    ]
