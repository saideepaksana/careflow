import uuid
from collections.abc import Iterator
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

from careflow.agents.baseline import StopReason, run_baseline_agent
from careflow.agents.intake import Turn
from careflow.agents.tools import PatientTools
from careflow.api.sessions import SessionStore
from careflow.config import MESSAGE_MAX_CHARS, load_settings
from careflow.db import repository
from careflow.db.connection import Connection, connect
from careflow.llm.gateway import LLM, build_llm

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


def current_patient(request: Request, authorization: Annotated[str, Header()] = "") -> str:
    scheme, _, token = authorization.partition(" ")
    patient_id = request.app.state.sessions.patient_for(token) if scheme == "Bearer" else None
    if patient_id is None:
        raise HTTPException(status_code=401, detail="not signed in")
    return patient_id


Db = Annotated[Connection, Depends(get_conn)]
PatientId = Annotated[str, Depends(current_patient)]


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


@router.post("/conversations/{conversation_id}/messages")
def post_message(
    conversation_id: str,
    body: MessageIn,
    patient_id: PatientId,
    conn: Db,
    llm: Annotated[LLM, Depends(get_llm)],
) -> ReplyOut:
    require_conversation(conn, conversation_id, patient_id)
    history = [
        Turn(role=row["role"], text=row["content"])
        for row in repository.list_messages(conn, conversation_id)
        if row["role"] in CHAT_ROLES
    ]
    repository.insert_message(conn, conversation_id, "patient", body.text)
    tools = PatientTools(conn, patient_id, conversation_id)
    result = run_baseline_agent(llm, tools, body.text, history)
    repository.insert_message(conn, conversation_id, "assistant", result.reply)
    return ReplyOut(reply=result.reply, stop_reason=result.stop_reason)


def create_app(llm: LLM | None = None) -> FastAPI:
    app = FastAPI(title="CareFlow")
    app.state.settings = load_settings()
    app.state.sessions = SessionStore()
    app.state.llm = llm
    app.include_router(router)
    return app


app = create_app()
