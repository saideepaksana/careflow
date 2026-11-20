import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from careflow.agents.intake import Turn
from careflow.api import coordinator
from careflow.api.deps import (
    Checkpoints,
    Db,
    Llm,
    Memory,
    PathId,
    PatientId,
    Storable,
    Workflow,
    exclusive,
)
from careflow.api.sessions import SessionStore
from careflow.config import ID_MAX_CHARS, MESSAGE_MAX_CHARS, load_settings
from careflow.db import repository
from careflow.db.connection import Connection
from careflow.graph.nodes import WorkflowDeps
from careflow.graph.workflow import (
    Checkpointer,
    NoPendingInterrupt,
    RunContext,
    RunResult,
    resume_run,
    start_run,
)
from careflow.llm.gateway import LLM, LLMOutputError, LLMUnavailableError
from careflow.memory.embeddings import Embedder
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
from careflow.observability.tracing import setup_tracing, traced_request
from careflow.safety.gate import red_flag_reasons

CHAT_ROLES = ("patient", "assistant")

router = APIRouter(prefix="/api")


class PatientOut(BaseModel):
    id: str
    name: str


class LoginIn(BaseModel):
    patient_id: Storable = Field(max_length=ID_MAX_CHARS)


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
    text: Storable = Field(min_length=1, max_length=MESSAGE_MAX_CHARS)


class ConfirmIn(BaseModel):
    approved: bool


class ReplyOut(BaseModel):
    reply: str
    status: str
    confirmation: str | None


def reply_from(result: RunResult) -> ReplyOut:
    return ReplyOut(
        reply="\n\n".join(result.messages),
        status=result.status,
        confirmation=result.confirmation,
    )


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
def list_messages(conversation_id: PathId, patient_id: PatientId, conn: Db) -> list[MessageOut]:
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
    conversation_id: PathId,
    body: MessageIn,
    patient_id: PatientId,
    conn: Db,
    llm: Llm,
    embedder: Memory,
    deps: Workflow,
    checkpointer: Checkpoints,
) -> ReplyOut:
    require_conversation(conn, conversation_id, patient_id)
    with exclusive(conn, conversation_id):
        pending = repository.pending_confirmation(conn, conversation_id)
        if pending and not red_flag_reasons(body.text):
            raise HTTPException(status_code=409, detail="please answer the pending confirmation")
        if pending:
            decline_pending(deps, checkpointer, pending)
        return run_message(
            conn, llm, embedder, deps, checkpointer, conversation_id, patient_id, body.text
        )


def decline_pending(deps: WorkflowDeps, checkpointer: Checkpointer, thread_id: str) -> None:
    """A red flag must not wait behind a yes/no question, so the pending change is declined."""
    try:
        resume_run(deps, checkpointer, thread_id, "confirmation", False)
    except NoPendingInterrupt:
        repository.set_run_status(deps.conn, thread_id, "failed")


def run_message(
    conn: Connection,
    llm: LLM,
    embedder: Embedder,
    deps: WorkflowDeps,
    checkpointer: Checkpointer,
    conversation_id: str,
    patient_id: str,
    text: str,
) -> ReplyOut:
    with traced_request("api.message", **{"careflow.patient_id": patient_id}):
        memory = refresh_working_memory(llm, conn, conversation_id)
        repository.insert_message(conn, conversation_id, "patient", text)
        context = RunContext(
            summary=render_summary(memory.summary),
            recent=memory.recent,
            memories=recall(conn, embedder, patient_id, text),
        )
        result = start_run(deps, checkpointer, conversation_id, patient_id, text, context)
    return reply_from(result)


@router.post("/conversations/{conversation_id}/confirm")
def confirm(
    conversation_id: PathId,
    body: ConfirmIn,
    patient_id: PatientId,
    conn: Db,
    deps: Workflow,
    checkpointer: Checkpoints,
) -> ReplyOut:
    require_conversation(conn, conversation_id, patient_id)
    with exclusive(conn, conversation_id):
        if repository.get_conversation_state(conn, conversation_id)["ended_at"] is not None:
            raise HTTPException(status_code=409, detail="conversation has ended")
        thread_id = repository.pending_confirmation(conn, conversation_id)
        if thread_id is None:
            raise HTTPException(status_code=409, detail="nothing to confirm")
        answer = "Yes" if body.approved else "No"
        repository.insert_message(conn, conversation_id, "patient", answer)
        with traced_request("api.confirm", **{"careflow.patient_id": patient_id}):
            result = resume_or_conflict(deps, checkpointer, thread_id, body.approved)
    return reply_from(result)


def resume_or_conflict(
    deps: WorkflowDeps, checkpointer: Checkpointer, thread_id: str, approved: bool
) -> RunResult:
    try:
        return resume_run(deps, checkpointer, thread_id, "confirmation", approved)
    except NoPendingInterrupt as error:
        raise HTTPException(status_code=409, detail="nothing to confirm") from error


@router.post("/conversations/{conversation_id}/end")
def end_conversation(
    conversation_id: PathId, patient_id: PatientId, conn: Db, llm: Llm, embedder: Memory
) -> MemoryWriteResult:
    require_conversation(conn, conversation_id, patient_id)
    with exclusive(conn, conversation_id):
        memory, _ = load_working_memory(conn, conversation_id)
        if memory.summary is None and not memory.recent:
            repository.end_conversation(conn, conversation_id)
            return MemoryWriteResult()
        try:
            with traced_request("api.end", **{"careflow.patient_id": patient_id}):
                digest = digest_session(llm, memory.summary, memory.recent)
        except (LLMOutputError, LLMUnavailableError) as error:
            raise HTTPException(status_code=503, detail="memory could not be written") from error
        with conn.transaction():
            repository.end_conversation(conn, conversation_id)
            return write_session_memory(conn, embedder, patient_id, conversation_id, digest)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_tracing(app.state.settings.otel_endpoint)
    yield


async def validation_failed(_: Request, error: RequestValidationError) -> JSONResponse:
    """422 without echoing the input, which may hold patient text or unencodable characters."""
    details = [{k: v for k, v in item.items() if k != "input"} for item in error.errors()]
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(details)})


def create_app(llm: LLM | None = None) -> FastAPI:
    app = FastAPI(title="CareFlow", lifespan=lifespan)
    app.state.settings = load_settings()
    app.state.sessions = SessionStore()
    app.state.llm = llm
    app.state.embedder = None
    app.state.reranker = None
    app.state.checkpointer = None
    app.add_exception_handler(RequestValidationError, validation_failed)
    app.include_router(router)
    app.include_router(coordinator.router)
    return app


app = create_app()
