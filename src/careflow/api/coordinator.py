import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel

from careflow.api.deps import Checkpoints, Db, Workflow
from careflow.db import repository
from careflow.graph.workflow import resume_run

CoordinatorToken = Annotated[str, Header(alias="X-Coordinator-Token")]


def require_coordinator(request: Request, token: CoordinatorToken = "") -> None:
    expected = request.app.state.settings.coordinator_token
    if not expected or not secrets.compare_digest(token, expected):
        raise HTTPException(status_code=403, detail="coordinator token required")


router = APIRouter(prefix="/api/coordinator", dependencies=[Depends(require_coordinator)])


class TaskOut(BaseModel):
    id: int
    patient_id: str
    kind: str
    priority: str
    title: str
    detail: dict
    thread_id: str | None


class DecisionIn(BaseModel):
    approved: bool
    note: str = ""


class DecisionOut(BaseModel):
    task_id: int
    run_status: str | None


@router.get("/tasks")
def list_tasks(conn: Db) -> list[TaskOut]:
    return [TaskOut(**row) for row in repository.list_open_tasks(conn)]


@router.post("/tasks/{task_id}/decision")
def decide(
    task_id: int, body: DecisionIn, conn: Db, deps: Workflow, checkpointer: Checkpoints
) -> DecisionOut:
    task = repository.get_task(conn, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    if task["status"] != "open":
        raise HTTPException(status_code=409, detail="task already resolved")
    run = repository.get_run(conn, task["thread_id"]) if task["thread_id"] else None
    if task["kind"] == "approval" and run and run["status"] == "awaiting_coordinator":
        result = resume_run(deps, checkpointer, task["thread_id"], "coordinator", body.model_dump())
        return DecisionOut(task_id=task_id, run_status=result.status)
    repository.resolve_task(conn, task_id, body.note)
    if body.note and task["conversation_id"]:
        repository.insert_message(conn, task["conversation_id"], "coordinator", body.note)
    return DecisionOut(task_id=task_id, run_status=run["status"] if run else None)
