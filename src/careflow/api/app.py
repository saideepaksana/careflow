import uuid
from collections.abc import Iterator
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

from careflow.agents.baseline import AgentContext, StopReason, run_baseline_agent
from careflow.agents.intake import Turn
from careflow.agents.tools import PatientTools
from careflow.api.sessions import SessionStore
from careflow.config import MESSAGE_MAX_CHARS, load_settings
from careflow.db import repository
from careflow.db.connection import Connection, connect
from careflow.knowledge.rerank import FastReranker, Reranker
from careflow.llm.gateway import LLM, LLMOutputError, LLMUnavailableError, build_llm
from careflow.memory.embeddings import Embedder, FastEmbedder
from careflow.memory.manager import (
    MemoryWriteResult,
    digest_session,
    recall,
    write_session_memory,
)
from careflow.memory.working import (
    SessionSummary,
    WorkingMemory,
    fold_if_needed,
    render_summary,
)

CHAT_ROLES = ("patient", "assistant")

router = APIRouter(prefix="/api")


class PatientOut(BaseModel):
    id: str
    name: str


class LoginIn(BaseModel):
    patient_id: str


class LoginOut(BaseModel):
    token: str
    patient_name: str


class ConversationOut(BaseModel):
    conversation_id: str


class MessageOut(BaseModel):
    role: str
    content: str
    created_at: datetime


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=MESSAGE_MAX_CHARS)


class ReplyOut(BaseModel):
    reply: str
    stop_reason: StopReason


def get_conn(request: Request) -> Iterator[Connection]:
    with connect(request.app.state.settings.database_url) as conn:
        yield conn


def get_llm(request: Request) -> LLM:
    state = request.app.state
    if state.llm is None:
        state.llm = build_llm(state.settings)
    return state.llm


def get_embedder(request: Request) -> Embedder:
    state = request.app.state
    if state.embedder is None:
        state.embedder = FastEmbedder()
    return state.embedder


def get_reranker(request: Request) -> Reranker:
    state = request.app.state
    if state.reranker is None:
        state.reranker = FastReranker()
    return state.reranker


def current_patient(request: Request, authorization: Annotated[str, Header()] = "") -> str:
    scheme, _, token = authorization.partition(" ")
    patient_id = request.app.state.sessions.patient_for(token) if scheme == "Bearer" else None
    if patient_id is None:
        raise HTTPException(status_code=401, detail="not signed in")
    return patient_id


Db = Annotated[Connection, Depends(get_conn)]
PatientId = Annotated[str, Depends(current_patient)]
Llm = Annotated[LLM, Depends(get_llm)]
Memory = Annotated[Embedder, Depends(get_embedder)]
Ranker = Annotated[Reranker, Depends(get_reranker)]


def require_conversation(conn: Connection, conversation_id: str, patient_id: str) -> None:
    if not repository.owns_conversation(conn, conversation_id, patient_id):
        raise HTTPException(status_code=404, detail="conversation not found")


@router.get("/patients")
def list_patients(conn: Db) -> list[PatientOut]:
    return [PatientOut(**row) for row in repository.list_patients(conn)]


@router.post("/login")
def login(body: LoginIn, request: Request, conn: Db) -> LoginOut:
    patient = repository.get_patient(conn, body.patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="patient not found")
    token = request.app.state.sessions.create(patient["id"])
    return LoginOut(token=token, patient_name=patient["name"])


@router.post("/conversations")
def create_conversation(patient_id: PatientId, conn: Db) -> ConversationOut:
    conversation_id = f"conv-{uuid.uuid4().hex[:12]}"
    repository.create_conversation(conn, conversation_id, patient_id)
    return ConversationOut(conversation_id=conversation_id)


@router.get("/conversations/{conversation_id}/messages")
def list_messages(conversation_id: str, patient_id: PatientId, conn: Db) -> list[MessageOut]:
    require_conversation(conn, conversation_id, patient_id)
    return [MessageOut(**row) for row in repository.list_messages(conn, conversation_id)]


def load_working_memory(conn: Connection, conversation_id: str) -> tuple[WorkingMemory, list[int]]:
    state = repository.get_conversation_state(conn, conversation_id)
    if state["ended_at"] is not None:
        raise HTTPException(status_code=409, detail="conversation has ended")
    rows = [
        row
        for row in repository.list_messages_after(
            conn, conversation_id, state["summarized_through"]
        )
        if row["role"] in CHAT_ROLES
    ]
    summary = SessionSummary.model_validate_json(state["summary"]) if state["summary"] else None
    memory = WorkingMemory(
        summary=summary,
        recent=[Turn(role=row["role"], text=row["content"]) for row in rows],
        summarized_through=state["summarized_through"],
    )
    return memory, [row["id"] for row in rows]


def refresh_working_memory(llm: LLM, conn: Connection, conversation_id: str) -> WorkingMemory:
    memory, turn_ids = load_working_memory(conn, conversation_id)
    try:
        folded = fold_if_needed(llm, memory, turn_ids)
    except (LLMOutputError, LLMUnavailableError):
        return memory
    if folded.summarized_through != memory.summarized_through:
        summary_json = folded.summary.model_dump_json() if folded.summary else ""
        repository.save_summary(conn, conversation_id, summary_json, folded.summarized_through)
    return folded


@router.post("/conversations/{conversation_id}/messages")
def post_message(
    conversation_id: str,
    body: MessageIn,
    patient_id: PatientId,
    conn: Db,
    llm: Llm,
    embedder: Memory,
    reranker: Ranker,
) -> ReplyOut:
    require_conversation(conn, conversation_id, patient_id)
    memory = refresh_working_memory(llm, conn, conversation_id)
    repository.insert_message(conn, conversation_id, "patient", body.text)
    context = AgentContext(
        summary=render_summary(memory.summary),
        recent=memory.recent,
        memories=recall(conn, embedder, patient_id, body.text),
    )
    tools = PatientTools(conn, patient_id, conversation_id, embedder, reranker)
    result = run_baseline_agent(llm, tools, body.text, context)
    repository.insert_message(conn, conversation_id, "assistant", result.reply)
    return ReplyOut(reply=result.reply, stop_reason=result.stop_reason)


@router.post("/conversations/{conversation_id}/end")
def end_conversation(
    conversation_id: str, patient_id: PatientId, conn: Db, llm: Llm, embedder: Memory
) -> MemoryWriteResult:
    require_conversation(conn, conversation_id, patient_id)
    memory, _ = load_working_memory(conn, conversation_id)
    if memory.summary is None and not memory.recent:
        repository.end_conversation(conn, conversation_id)
        return MemoryWriteResult()
    try:
        digest = digest_session(llm, memory.summary, memory.recent)
    except (LLMOutputError, LLMUnavailableError) as error:
        raise HTTPException(status_code=503, detail="memory could not be written") from error
    repository.end_conversation(conn, conversation_id)
    return write_session_memory(conn, embedder, patient_id, conversation_id, digest)


def create_app(llm: LLM | None = None) -> FastAPI:
    app = FastAPI(title="CareFlow")
    app.state.settings = load_settings()
    app.state.sessions = SessionStore()
    app.state.llm = llm
    app.state.embedder = None
    app.state.reranker = None
    app.include_router(router)
    return app


app = create_app()
