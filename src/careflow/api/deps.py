from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Path, Request
from pydantic import AfterValidator

from careflow.config import ID_MAX_CHARS
from careflow.db import repository
from careflow.db.checkpointer import is_alive, open_checkpointer
from careflow.db.connection import Connection, connect
from careflow.graph.nodes import WorkflowDeps
from careflow.graph.workflow import Checkpointer
from careflow.knowledge.rerank import FastReranker, Reranker
from careflow.llm.gateway import LLM, build_llm
from careflow.memory.embeddings import Embedder, FastEmbedder


def get_conn(request: Request) -> Iterator[Connection]:
    with connect(request.app.state.settings.database_url, autocommit=True) as conn:
        yield conn


def require_storable(text: str) -> str:
    """Reject text PostgreSQL cannot store: NUL bytes and unpaired surrogates."""
    if "\x00" in text:
        raise ValueError("text contains a NUL byte")
    text.encode()
    return text


Storable = Annotated[str, AfterValidator(require_storable)]
PathId = Annotated[str, Path(max_length=ID_MAX_CHARS), AfterValidator(require_storable)]


@contextmanager
def exclusive(conn: Connection, conversation_id: str) -> Iterator[None]:
    with repository.conversation_lock(conn, conversation_id) as locked:
        if not locked:
            raise HTTPException(status_code=423, detail="still working on the previous request")
        yield


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


def get_checkpointer(request: Request) -> Checkpointer:
    state = request.app.state
    if state.checkpointer is not None and not is_alive(state.checkpointer):
        state.checkpointer.conn.close()
        state.checkpointer = None
    if state.checkpointer is None:
        state.checkpointer = open_checkpointer(state.settings.database_url)
    return state.checkpointer


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
Checkpoints = Annotated[Checkpointer, Depends(get_checkpointer)]


def workflow_deps(conn: Db, llm: Llm, embedder: Memory, reranker: Ranker) -> WorkflowDeps:
    return WorkflowDeps(conn=conn, llm=llm, embedder=embedder, reranker=reranker)


Workflow = Annotated[WorkflowDeps, Depends(workflow_deps)]
