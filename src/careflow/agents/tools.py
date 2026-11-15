import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from careflow.agents.intake import Specialty, Urgency
from careflow.config import (
    IDEMPOTENCY_HASH_CHARS,
    RETRIEVAL_RESULT_MAX_CHARS,
    TASK_TITLE_MAX_CHARS,
    TOOL_ERROR_MAX_CHARS,
)
from careflow.db import repository
from careflow.db.connection import Connection
from careflow.knowledge.rerank import Reranker
from careflow.knowledge.search import retrieve
from careflow.memory.embeddings import Embedder

AUDIT_ACTOR = "baseline_agent"


class NoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FindSlotsArgs(NoArgs):
    specialty: Specialty
    start_date: date
    end_date: date


class SearchDocumentsArgs(NoArgs):
    query: str = Field(min_length=1)


class BookAppointmentArgs(NoArgs):
    slot_id: str
    care_plan_item_id: str | None = None


class RescheduleAppointmentArgs(NoArgs):
    appointment_id: str
    new_slot_id: str


class CancelAppointmentArgs(NoArgs):
    appointment_id: str


class CreateCoordinatorTaskArgs(NoArgs):
    priority: Urgency
    title: str = Field(max_length=TASK_TITLE_MAX_CHARS)
    detail: str


@dataclass(frozen=True)
class ToolSpec:
    description: str
    args_model: type[BaseModel]
    write: bool


TOOLS: dict[str, ToolSpec] = {
    "get_care_plan": ToolSpec("Read the patient's current care plan.", NoArgs, False),
    "list_appointments": ToolSpec("List the patient's booked appointments.", NoArgs, False),
    "find_slots": ToolSpec(
        "Find free appointment slots for a specialty between two dates.", FindSlotsArgs, False
    ),
    "search_documents": ToolSpec(
        "Search the patient's current care documents and hospital guides.",
        SearchDocumentsArgs,
        False,
    ),
    "book_appointment": ToolSpec(
        "Book a free slot, optionally for a care-plan item.", BookAppointmentArgs, True
    ),
    "reschedule_appointment": ToolSpec(
        "Move a booked appointment to a new free slot.", RescheduleAppointmentArgs, True
    ),
    "cancel_appointment": ToolSpec("Cancel a booked appointment.", CancelAppointmentArgs, True),
    "create_coordinator_task": ToolSpec(
        "Ask a nurse coordinator to follow up with the patient.", CreateCoordinatorTaskArgs, True
    ),
}


def idempotency_key(conversation_id: str, tool: str, args: BaseModel) -> str:
    canonical = json.dumps(args.model_dump(mode="json"), sort_keys=True)
    digest = hashlib.sha256(canonical.encode()).hexdigest()[:IDEMPOTENCY_HASH_CHARS]
    return f"{conversation_id}:{tool}:{digest}"


def to_json_safe(value: object) -> object:
    return json.loads(json.dumps(value, default=lambda item: item.isoformat()))


class PatientTools:
    """Tools bound to one session's patient; the model never chooses the patient."""

    def __init__(
        self,
        conn: Connection,
        patient_id: str,
        conversation_id: str,
        embedder: Embedder,
        reranker: Reranker,
    ) -> None:
        self.conn = conn
        self.patient_id = patient_id
        self.conversation_id = conversation_id
        self.embedder = embedder
        self.reranker = reranker

    def describe(self) -> str:
        lines = [
            f"- {name}: {spec.description} Args schema: "
            f"{json.dumps(spec.args_model.model_json_schema()['properties'])}"
            for name, spec in TOOLS.items()
        ]
        return "\n".join(lines)

    def call_tool(self, name: str, args: dict) -> dict:
        result = self.run_tool(name, args)
        repository.insert_audit_event(
            self.conn,
            self.patient_id,
            AUDIT_ACTOR,
            "tool_call",
            {"tool": name, "args": to_json_safe(args), "result": result},
        )
        return result

    def run_tool(self, name: str, args: dict) -> dict:
        spec = TOOLS.get(name)
        if spec is None:
            return {"ok": False, "error": "unknown_tool"}
        try:
            parsed = spec.args_model.model_validate(args)
        except ValidationError as error:
            return {
                "ok": False,
                "error": "invalid_args",
                "detail": str(error)[:TOOL_ERROR_MAX_CHARS],
            }
        if spec.write:
            key = idempotency_key(self.conversation_id, name, parsed)
            return self.write_handlers()[name](parsed, key)
        data = self.read_handlers()[name](parsed)
        return {"ok": True, "data": to_json_safe(data)}

    def read_handlers(self) -> dict[str, Callable[[BaseModel], object]]:
        conn, patient_id = self.conn, self.patient_id
        return {
            "get_care_plan": lambda _: repository.get_current_care_plan(conn, patient_id),
            "list_appointments": lambda _: repository.list_appointments(conn, patient_id),
            "find_slots": lambda a: repository.find_free_slots(
                conn, a.specialty.value, a.start_date, a.end_date
            ),
            "search_documents": lambda a: self.search_documents(a.query),
        }

    def search_documents(self, query: str) -> list[dict]:
        chunks = retrieve(self.conn, self.embedder, self.reranker, self.patient_id, query)
        return [
            {
                "source": chunk.id,
                "title": chunk.title,
                "heading": chunk.heading,
                "text": chunk.content[:RETRIEVAL_RESULT_MAX_CHARS],
            }
            for chunk in chunks
        ]

    def write_handlers(self) -> dict[str, Callable[[BaseModel, str], dict]]:
        conn, patient_id = self.conn, self.patient_id
        return {
            "book_appointment": lambda a, key: repository.book_appointment(
                conn, patient_id, a.slot_id, a.care_plan_item_id, key
            ),
            "reschedule_appointment": lambda a, key: repository.reschedule_appointment(
                conn, patient_id, a.appointment_id, a.new_slot_id, key
            ),
            "cancel_appointment": lambda a, key: repository.cancel_appointment(
                conn, patient_id, a.appointment_id, key
            ),
            "create_coordinator_task": lambda a, key: repository.create_coordinator_task(
                conn, patient_id, a.priority.value, a.title, a.detail, key
            ),
        }
