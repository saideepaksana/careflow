from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request

from careflow.db.checkpointer import open_checkpointer
from careflow.db.connection import Connection, connect
from careflow.graph.nodes import WorkflowDeps
from careflow.graph.workflow import Checkpointer
from careflow.knowledge.rerank import FastReranker, Reranker
from careflow.llm.gateway import LLM, build_llm
from careflow.memory.embeddings import Embedder, FastEmbedder


def get_conn(request: Request) -> Iterator[Connection]:
    with connect(request.app.state.settings.database_url, autocommit=True) as conn:
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


def get_checkpointer(request: Request) -> Checkpointer:
    state = request.app.state
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
