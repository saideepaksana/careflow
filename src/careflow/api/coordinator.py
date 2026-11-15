import secrets
from datetime import date, datetime
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel

from careflow import clock
from careflow.api.deps import Checkpoints, Db, Workflow
from careflow.config import CLINIC_TIMEZONE, TIMELINE_LIMIT
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
    patient_name: str
    created_at: datetime
    kind: str
    priority: str
    title: str
    detail: dict
    thread_id: str | None


class PatientOverview(BaseModel):
    id: str
    name: str
    diagnosis: str | None
    open_tasks: int


class TimelineEvent(BaseModel):
    at: datetime
    kind: str
    text: str
    detail: dict


ProgressStatus = Literal["booked", "late", "overdue", "open"]


class ProgressItem(BaseModel):
    id: str
    kind: str
    description: str
    due_date: date | None
    appointment_id: str | None
    starts_at: datetime | None
    status: ProgressStatus


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
    owns_run = run and repository.thread_patient(conn, run["thread_id"]) == task["patient_id"]
    if task["kind"] == "approval" and owns_run and run["status"] == "awaiting_coordinator":
        result = resume_run(deps, checkpointer, task["thread_id"], "coordinator", body.model_dump())
        return DecisionOut(task_id=task_id, run_status=result.status)
    repository.resolve_task(conn, task_id, body.note)
    if body.note and task["conversation_id"]:
        repository.insert_message(conn, task["conversation_id"], "coordinator", body.note)
    return DecisionOut(task_id=task_id, run_status=run["status"] if run else None)


@router.get("/patients")
def list_patients(conn: Db) -> list[PatientOverview]:
    return [PatientOverview(**row) for row in repository.list_patient_overview(conn)]


def require_patient(conn: Db, patient_id: str) -> None:
    if repository.get_patient(conn, patient_id) is None:
        raise HTTPException(status_code=404, detail="patient not found")


@router.get("/patients/{patient_id}/timeline")
def timeline(patient_id: str, conn: Db) -> list[TimelineEvent]:
    require_patient(conn, patient_id)
    rows = repository.patient_timeline(conn, patient_id, TIMELINE_LIMIT)
    return [TimelineEvent(**row) for row in rows]


def progress_status(due_date: date | None, starts_at: datetime | None) -> ProgressStatus:
    if starts_at is not None:
        local_day = starts_at.astimezone(ZoneInfo(CLINIC_TIMEZONE)).date()
        return "late" if due_date and local_day > due_date else "booked"
    return "overdue" if due_date and due_date < clock.today() else "open"


@router.get("/patients/{patient_id}/progress")
def progress(patient_id: str, conn: Db) -> list[ProgressItem]:
    require_patient(conn, patient_id)
    return [
        ProgressItem(**row, status=progress_status(row["due_date"], row["starts_at"]))
        for row in repository.plan_progress_rows(conn, patient_id)
    ]
