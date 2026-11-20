import time
import uuid
from collections import deque
from dataclasses import replace

from fastapi.testclient import TestClient

from careflow.agents.baseline import AgentContext, run_baseline_agent
from careflow.agents.tools import PatientTools
from careflow.api import app as api
from careflow.api.app import create_app
from careflow.config import (
    CHARS_PER_TOKEN,
    EVAL_OUTPUT_TOKEN_ESTIMATE,
    EVAL_TOKENS_PER_MINUTE,
    Settings,
)
from careflow.db import repository
from careflow.db.connection import connect
from careflow.evaluation.scenarios import ERROR_REPLY_PREFIX
from careflow.knowledge.rerank import Reranker
from careflow.llm.gateway import LLM, LLMBudgetExceeded, LLMRejectedError, LLMUnavailableError
from careflow.memory.embeddings import Embedder
from careflow.memory.manager import recall
from careflow.memory.working import render_summary
from careflow.observability.budget import current_budget
from careflow.observability.tracing import traced_request

WINDOW_SECONDS = 60
EVAL_COORDINATOR_TOKEN = "eval-coordinator"
CONFIRM_TEXT = {True: "Yes, please go ahead.", False: "No, please don't change anything."}


class RecordingLLM:
    """Paces calls under a tokens-per-minute target and counts provider outages."""

    def __init__(self, inner: LLM, tokens_per_minute: int = EVAL_TOKENS_PER_MINUTE) -> None:
        self.inner = inner
        self.tokens_per_minute = tokens_per_minute
        self.window: deque[tuple[float, int]] = deque()
        self.unavailable = 0
        self.throttled_seconds = 0.0

    def complete(self, system: str, user: str) -> str:
        self.wait_for((len(system) + len(user)) // CHARS_PER_TOKEN + EVAL_OUTPUT_TOKEN_ESTIMATE)
        try:
            return self.inner.complete(system, user)
        except (LLMBudgetExceeded, LLMRejectedError):
            raise
        except LLMUnavailableError:
            self.unavailable += 1
            raise

    def wait_for(self, tokens: int) -> None:
        while True:
            now = time.monotonic()
            while self.window and now - self.window[0][0] >= WINDOW_SECONDS:
                self.window.popleft()
            used = sum(amount for _, amount in self.window)
            if not self.window or used + tokens <= self.tokens_per_minute:
                self.window.append((now, tokens))
                return
            pause = WINDOW_SECONDS - (now - self.window[0][0])
            time.sleep(pause)
            self.throttled_seconds += pause
            budget = current_budget()
            if budget is not None:
                budget.pause(pause)


class CareFlowSystem:
    """The full API on the evaluation database, driven through FastAPI's TestClient."""

    def __init__(
        self, settings: Settings, llm: LLM, embedder: Embedder, reranker: Reranker, patient_id: str
    ) -> None:
        app = create_app(llm)
        app.state.settings = replace(settings, coordinator_token=EVAL_COORDINATOR_TOKEN)
        app.state.embedder, app.state.reranker = embedder, reranker
        self.app, self.client = app, TestClient(app, raise_server_exceptions=False)
        token = self.client.post("/api/login", json={"patient_id": patient_id}).json()["token"]
        self.headers = {"Authorization": f"Bearer {token}"}
        self.coordinator_headers = {"X-Coordinator-Token": EVAL_COORDINATOR_TOKEN}
        self.patient_id, self.conversation_id = patient_id, ""

    def say(self, text: str) -> tuple[list[str], bool]:
        if not self.conversation_id:
            created = self.client.post("/api/conversations", headers=self.headers).json()
            self.conversation_id = created["conversation_id"]
        path = f"/api/conversations/{self.conversation_id}/messages"
        return [
            reply_text(self.client.post(path, json={"text": text}, headers=self.headers))
        ], False

    def confirm(self, approved: bool) -> tuple[list[str], bool]:
        if not self.conversation_id:
            return [], True
        path = f"/api/conversations/{self.conversation_id}/confirm"
        response = self.client.post(path, json={"approved": approved}, headers=self.headers)
        return ([], True) if response.status_code == 409 else ([reply_text(response)], False)

    def coordinator(self, approved: bool) -> tuple[list[str], bool]:
        tasks = self.client.get("/api/coordinator/tasks", headers=self.coordinator_headers).json()
        mine = [t for t in tasks if t["patient_id"] == self.patient_id and t["kind"] == "approval"]
        for task in mine:
            path = f"/api/coordinator/tasks/{task['id']}/decision"
            self.client.post(
                path, json={"approved": approved, "note": ""}, headers=self.coordinator_headers
            )
        return self.new_messages(), not mine

    def new_messages(self) -> list[str]:
        path = f"/api/conversations/{self.conversation_id}/messages"
        messages = self.client.get(path, headers=self.headers).json()
        return [m["content"] for m in messages[-1:] if m["role"] == "assistant"]

    def end_session(self) -> tuple[list[str], bool]:
        if not self.conversation_id:
            return [], True
        self.client.post(f"/api/conversations/{self.conversation_id}/end", headers=self.headers)
        self.conversation_id = ""
        return [], False

    def close(self) -> None:
        if self.app.state.checkpointer is not None:
            self.app.state.checkpointer.conn.close()


def reply_text(response: object) -> str:
    if response.status_code != 200:
        return f"{ERROR_REPLY_PREFIX}{response.status_code}"
    return response.json()["reply"]


class BaselineSystem:
    """The M2 single agent with the same memory, tools and search, on the evaluation database."""

    def __init__(
        self, settings: Settings, llm: LLM, embedder: Embedder, reranker: Reranker, patient_id: str
    ) -> None:
        self.conn = connect(settings.database_url, autocommit=True)
        self.llm, self.embedder, self.reranker = llm, embedder, reranker
        self.patient_id, self.conversation_id = patient_id, ""

    def say(self, text: str) -> tuple[list[str], bool]:
        if not self.conversation_id:
            self.conversation_id = f"conv-{uuid.uuid4().hex[:12]}"
            repository.create_conversation(self.conn, self.conversation_id, self.patient_id)
        with traced_request("baseline.turn", **{"careflow.patient_id": self.patient_id}):
            return [self.turn(text)], False

    def turn(self, text: str) -> str:
        memory = api.refresh_working_memory(self.llm, self.conn, self.conversation_id)
        repository.insert_message(self.conn, self.conversation_id, "patient", text)
        context = AgentContext(
            summary=render_summary(memory.summary),
            recent=memory.recent,
            memories=recall(self.conn, self.embedder, self.patient_id, text),
        )
        tools = PatientTools(
            self.conn, self.patient_id, self.conversation_id, self.embedder, self.reranker
        )
        result = run_baseline_agent(self.llm, tools, text, context)
        repository.insert_message(self.conn, self.conversation_id, "assistant", result.reply)
        return result.reply

    def confirm(self, approved: bool) -> tuple[list[str], bool]:
        return self.say(CONFIRM_TEXT[approved])

    def coordinator(self, approved: bool) -> tuple[list[str], bool]:
        return [], True

    def end_session(self) -> tuple[list[str], bool]:
        if not self.conversation_id:
            return [], True
        api.end_conversation(
            self.conversation_id, self.patient_id, self.conn, self.llm, self.embedder
        )
        self.conversation_id = ""
        return [], False

    def close(self) -> None:
        self.conn.close()
