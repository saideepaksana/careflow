import json

import pytest
from fastapi.testclient import TestClient

from careflow.api.app import create_app
from careflow.config import Settings
from careflow.llm.gateway import FakeLLM
from careflow.memory.embeddings import FakeEmbedder


@pytest.fixture
def client(seeded_db_url: str) -> TestClient:
    llm = FakeLLM(
        [
            json.dumps({"action": "reply", "reply": "Your visit is on Wednesday."}),
            json.dumps({"episode": "Asked when the visit is.", "facts": []}),
        ]
    )
    app = create_app(llm)
    app.state.settings = Settings(database_url=seeded_db_url)
    app.state.embedder = FakeEmbedder()
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
