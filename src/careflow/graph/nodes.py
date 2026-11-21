from dataclasses import dataclass
from datetime import timedelta

from langgraph.types import interrupt
from pydantic import BaseModel, ValidationError

from careflow import clock
from careflow.agents.careplan import answer_question
from careflow.agents.intake import (
    AppointmentAction,
    IntakeItem,
    IntakeRecord,
    ItemKind,
    Specialty,
    Turn,
    run_intake,
)
from careflow.agents.scheduler import (
    SchedulingPlan,
    SchedulingRequest,
    choose_slot,
    interpret_request,
)
from careflow.config import MAX_REPLANS, SLOT_DAYS_AHEAD, SLOT_SCAN_LIMIT, SUPERVISOR_MAX_STEPS
from careflow.db import repository
from careflow.db.connection import Connection
from careflow.graph import executor, replies
from careflow.graph.state import WorkflowState
from careflow.knowledge.rerank import Reranker
from careflow.knowledge.search import RetrievedChunk
from careflow.llm.gateway import LLM, LLMOutputError, LLMUnavailableError
from careflow.mcp_servers.client import CarePlanView, McpTools
from careflow.memory.embeddings import Embedder
from careflow.observability.budget import current_budget
from careflow.observability.tracing import current_trace_id
from careflow.safety.gate import EscalationLevel, GateDecision, evaluate_gate
from careflow.safety.verifier import Verdict, VerdictKind, verify_plan

LLM_ERRORS = (LLMOutputError, LLMUnavailableError)
BOOKABLE_KINDS = ("follow_up", "lab")
ITEM_ROUTES = {
    ItemKind.care_plan_question: "answer_question",
    ItemKind.appointment_request: "plan_schedule",
    ItemKind.symptom_report: "hand_off",
    ItemKind.clinical_request: "hand_off",
}
# Without an intake record the gate cannot check warning-sign readings, so err towards urgent.
HANDOFF_PRIORITIES = {"intake_failed": "urgent"}
ESCALATION_REPLIES = {
    EscalationLevel.EMERGENCY: replies.EMERGENCY_REPLY,
    EscalationLevel.URGENT: replies.URGENT_REPLY,
}


@dataclass
class WorkflowDeps:
    conn: Connection
    llm: LLM
    embedder: Embedder
    reranker: Reranker


class CoordinatorDecision(BaseModel):
    approved: bool
    note: str = ""


def item_order(record: IntakeRecord) -> tuple[list[int], list[str]]:
    """Items to handle, appointment requests last and only the first one; plus fixed replies."""
    kinds = [item.kind for item in record.items]
    handled = [i for i, kind in enumerate(kinds) if kind in ITEM_ROUTES]
    others = [i for i in handled if kinds[i] != ItemKind.appointment_request]
    appointments = [i for i in handled if kinds[i] == ItemKind.appointment_request]
    notes = [replies.SCOPE_REPLY] if ItemKind.other in kinds else []
    if len(appointments) > 1:
        notes.append(replies.ONE_CHANGE_REPLY)
    return others + appointments[:1], notes


def read_decision(raw: object) -> CoordinatorDecision:
    try:
        return CoordinatorDecision.model_validate(raw)
    except ValidationError:
        return CoordinatorDecision(approved=False)


def plan_specialty(
    tools: McpTools, view: CarePlanView | None, request: SchedulingRequest
) -> str | None:
    if request.action == AppointmentAction.reschedule and request.appointment_id:
        appointment = tools.read("get_appointment", {"appointment_id": request.appointment_id})
        return appointment["specialty"] if appointment else None
    if request.care_plan_item_id:
        items = {item.id: item for item in (view.items if view else [])}
        item = items.get(request.care_plan_item_id)
        return item.specialty if item else None
    return request.specialty.value if request.specialty else None


def find_slot(tools: McpTools, specialty: str, request: SchedulingRequest) -> dict | None:
    tomorrow = clock.today() + timedelta(days=1)
    earliest = max(request.earliest_date or tomorrow, tomorrow)
    latest = request.latest_date or clock.today() + timedelta(days=SLOT_DAYS_AHEAD)
    slots = tools.free_slots(specialty, earliest, latest, SLOT_SCAN_LIMIT)
    return choose_slot(request, [slot.model_dump() for slot in slots])


def cancel_plan(tools: McpTools, plan: SchedulingPlan) -> SchedulingPlan:
    if plan.appointment_id is None:
        return plan
    appointment = tools.read("get_appointment", {"appointment_id": plan.appointment_id})
    if not appointment:
        return plan
    shown = {"specialty": appointment["specialty"], "starts_at": appointment["starts_at"]}
    return SchedulingPlan.model_validate({**plan.model_dump(), **shown})


def build_plan(
    tools: McpTools, view: CarePlanView | None, request: SchedulingRequest
) -> SchedulingPlan:
    plan = SchedulingPlan(
        action=request.action,
        appointment_id=request.appointment_id,
        care_plan_item_id=request.care_plan_item_id,
    )
    if request.action == AppointmentAction.cancel:
        return cancel_plan(tools, plan)
    specialty = plan_specialty(tools, view, request)
    if specialty is None:
        return plan
    slot = find_slot(tools, specialty, request) or {}
    return plan.model_copy(
        update={
            "specialty": Specialty(specialty),
            "slot_id": slot.get("id"),
            "starts_at": slot.get("starts_at"),
            "clinician_name": slot.get("clinician_name"),
        }
    )


def budget_spent() -> bool:
    budget = current_budget()
    return budget is not None and budget.exceeded()


def capped(state: WorkflowState, steps: int) -> dict | None:
    """Stop routing at the step cap, or hand off once when the request budget is spent."""
    if steps > SUPERVISOR_MAX_STEPS:
        left = ",".join(str(i) for i in state.get("pending") or [])
        return {"steps": steps, "route": "finalize", "outcome": [*state["outcome"], f"cap:{left}"]}
    if budget_spent() and state.get("pending") != []:
        update = {
            "steps": steps,
            "pending": [],
            "current": None,
            "route": "hand_off",
            "handoff_reason": "budget",
        }
        return {**update, "outcome": [*state["outcome"], "budget"]}
    return None


def task_key(state: WorkflowState, node: str) -> str:
    return f"{state['thread_id']}:task:{node}:{state.get('current')}"


class WorkflowNodes:
    def __init__(self, deps: WorkflowDeps) -> None:
        self.deps = deps

    def post(self, state: WorkflowState, node: str, texts: list[str]) -> dict:
        visits = dict(state.get("visits", {}))
        visit = visits.get(node, 0) + 1
        visits[node] = visit
        text = " ".join(dict.fromkeys(part for part in texts if part))
        if text:
            key = f"{state['thread_id']}:msg:{node}:{visit}"
            repository.insert_message(
                self.deps.conn, state["conversation_id"], "assistant", text, key
            )
        return {"visits": visits, "replies": []}

    def tools(self, state: WorkflowState) -> McpTools:
        deps = self.deps
        return McpTools(deps.conn, state["patient_id"], deps.embedder, deps.reranker)

    def create_task(
        self, state: WorkflowState, node: str, kind: str, priority: str, title: str, detail: str
    ) -> dict:
        return executor.create_task(
            self.tools(state),
            task_key(state, node),
            kind,
            priority,
            title,
            detail,
            state["thread_id"],
        )

    def current_item(self, state: WorkflowState) -> IntakeItem:
        return IntakeRecord.model_validate(state["intake"]).items[state["current"]]

    def intake(self, state: WorkflowState) -> dict:
        recent = [Turn.model_validate(turn) for turn in state.get("recent", [])]
        try:
            record = run_intake(self.deps.llm, state["message"], recent)
        except LLM_ERRORS:
            return {"intake": None, "outcome": [*state["outcome"], "intake:failed"]}
        return {"intake": record.model_dump(mode="json")}

    def safety_gate(self, state: WorkflowState) -> dict:
        signs = repository.get_warning_signs(self.deps.conn, state["patient_id"])
        record = IntakeRecord.model_validate(state["intake"]) if state.get("intake") else None
        decision = evaluate_gate(state["message"], record, signs)
        route = "supervisor" if decision.level == EscalationLevel.NONE else "escalate"
        return {"gate": decision.model_dump(mode="json"), "route": route}

    def escalate(self, state: WorkflowState) -> dict:
        decision = GateDecision.model_validate(state["gate"])
        record = IntakeRecord.model_validate(state["intake"]) if state.get("intake") else None
        summaries = [item.summary for item in record.items] if record else []
        signs = repository.get_warning_signs(self.deps.conn, state["patient_id"])
        names = {sign["id"]: sign["description"] for sign in signs}
        reasons = [replies.escalation_reason(reason, names) for reason in decision.reasons]
        detail = f"Reasons: {'; '.join(reasons)}. Items: {' | '.join(summaries)}"
        title = f"{decision.level.value.capitalize()} escalation"
        self.create_task(state, "escalate", "escalation", decision.level.value, title, detail)
        reply = ESCALATION_REPLIES[decision.level]
        if record and any(item.kind == ItemKind.appointment_request for item in record.items):
            reply = f"{reply} {replies.HELD_CHANGE_REPLY}"
        return {
            "replies": [*state["replies"], reply],
            "outcome": [*state["outcome"], f"escalate:{decision.level.value}"],
        }

    def supervisor(self, state: WorkflowState) -> dict:
        steps = state["steps"] + 1
        if state.get("intake") is None:
            route = "hand_off" if state.get("pending") is None else "finalize"
            return {
                "steps": steps,
                "pending": [],
                "route": route,
                "handoff_reason": "intake_failed",
            }
        stop = capped(state, steps)
        if stop is not None:
            return stop
        pending, notes = state["pending"], []
        if pending is None:
            pending, notes = item_order(IntakeRecord.model_validate(state["intake"]))
        if not pending:
            replies_left = [*state["replies"], *notes]
            return {"steps": steps, "pending": [], "route": "finalize", "replies": replies_left}
        return self.dispatch(state, steps, pending, notes)

    def dispatch(
        self, state: WorkflowState, steps: int, pending: list[int], notes: list[str]
    ) -> dict:
        current = pending[0]
        kind = IntakeRecord.model_validate(state["intake"]).items[current].kind
        return {
            "steps": steps,
            "pending": pending[1:],
            "current": current,
            "route": ITEM_ROUTES[kind],
            "handoff_reason": kind.value,
            "replies": [*state["replies"], *notes],
            "plan": None,
            "verdict": None,
            "replans": 0,
            "feedback": "",
            "coordinator_approved": False,
        }

    def answer_question(self, state: WorkflowState) -> dict:
        item = self.current_item(state)
        found = self.tools(state).search(item.summary)
        chunks = [RetrievedChunk.model_validate(chunk) for chunk in found]
        result = answer_question(self.deps.llm, item.summary, chunks)
        if result.handed_off:
            detail = f"{item.summary} (reason: {replies.reason_label(result.handoff_reason)})"
            self.create_task(
                state, "answer_question", "handoff", "routine", "Question for a nurse", detail
            )
        label = f"answer:{result.handoff_reason or 'cited'}"
        return {"replies": [*state["replies"], result.reply], "outcome": [*state["outcome"], label]}

    def hand_off(self, state: WorkflowState) -> dict:
        reason = state["handoff_reason"]
        summary = self.handoff_summary(state)
        detail = f"{summary} (reason: {replies.reason_label(reason)})"
        priority = HANDOFF_PRIORITIES.get(reason, "routine")
        self.create_task(
            state, "hand_off", "handoff", priority, "Patient needs a coordinator", detail
        )
        return {
            "replies": [*state["replies"], replies.HANDOFF_REPLY],
            "outcome": [*state["outcome"], f"hand_off:{reason}"],
        }

    def handoff_summary(self, state: WorkflowState) -> str:
        if state.get("current") is not None:
            return self.current_item(state).summary
        if not state.get("intake"):
            return ""
        return " | ".join(
            item.summary for item in IntakeRecord.model_validate(state["intake"]).items
        )

    def plan_schedule(self, state: WorkflowState) -> dict:
        tools = self.tools(state)
        view = tools.care_plan()
        items = [item for item in (view.items if view else []) if item.kind in BOOKABLE_KINDS]
        try:
            request = interpret_request(
                self.deps.llm,
                self.current_item(state),
                [item.model_dump(mode="json") for item in items],
                tools.read("list_appointments") or [],
                state.get("memories", []),
                state["feedback"],
            )
        except LLM_ERRORS:
            return {"route": "hand_off", "handoff_reason": "planner_failed"}
        plan = build_plan(tools, view, request)
        replans = state["replans"] + (1 if state["feedback"] else 0)
        return {"plan": plan.model_dump(mode="json"), "replans": replans, "route": "verify"}

    def verify(self, state: WorkflowState) -> dict:
        plan = SchedulingPlan.model_validate(state["plan"])
        verdict = verify_plan(self.deps.conn, state["patient_id"], plan)
        update = {
            "verdict": verdict.model_dump(mode="json"),
            "outcome": [*state["outcome"], f"verify:{verdict.kind.value}:{verdict.reason}"],
        }
        if verdict.kind != VerdictKind.REJECTED:
            return {**update, "route": "ask_confirmation"}
        if verdict.fixable and state["replans"] < MAX_REPLANS:
            return {**update, "route": "plan_schedule", "feedback": verdict.reason}
        if verdict.fixable:
            return {
                **update,
                "route": "hand_off",
                "handoff_reason": f"replans_exhausted:{verdict.reason}",
            }
        reply = replies.rejected_reply(verdict.reason)
        return {**update, "route": "supervisor", "replies": [*state["replies"], reply]}

    def ask_confirmation(self, state: WorkflowState) -> dict:
        plan = SchedulingPlan.model_validate(state["plan"])
        verdict = Verdict.model_validate(state["verdict"])
        needs_approval = verdict.kind == VerdictKind.NEEDS_APPROVAL
        prompt = replies.confirmation_prompt(plan, needs_approval)
        posted = self.post(state, "ask_confirmation", [*state["replies"], prompt])
        answer = interrupt({"kind": "confirmation", "summary": prompt})
        if answer is not True:
            return {
                **posted,
                "route": "supervisor",
                "replies": [replies.NOT_CHANGED_REPLY],
                "outcome": [*state["outcome"], "declined"],
            }
        route = "await_coordinator" if needs_approval else "execute"
        return {**posted, "route": route, "outcome": [*state["outcome"], "confirmed"]}

    def await_coordinator(self, state: WorkflowState) -> dict:
        verdict = Verdict.model_validate(state["verdict"])
        prompt = replies.describe_change(SchedulingPlan.model_validate(state["plan"]), "their")
        detail = f"Patient confirmed: {prompt} (reason: {replies.reason_label(verdict.reason)})"
        task = self.create_task(
            state, "await_coordinator", "approval", "routine", "Approve change", detail
        )
        posted = self.post(state, "await_coordinator", [replies.APPROVAL_PENDING_REPLY])
        decision = read_decision(interrupt({"kind": "coordinator", "task_id": task["task_id"]}))
        executor.resolve_task(self.tools(state), task["task_id"], decision.note)
        label = f"coordinator:{'approved' if decision.approved else 'denied'}"
        update = {**posted, "outcome": [*state["outcome"], label]}
        if decision.approved:
            return {**update, "route": "execute", "coordinator_approved": True}
        return {**update, "route": "finalize", "replies": [replies.DENIED_REPLY]}

    def execute(self, state: WorkflowState) -> dict:
        plan = SchedulingPlan.model_validate(state["plan"])
        result = executor.execute_plan(
            self.deps.conn,
            self.tools(state),
            state["patient_id"],
            state["thread_id"],
            plan,
            state["coordinator_approved"],
        )
        ok = result.get("ok", False)
        reply = (
            replies.action_done_reply(plan) if ok else replies.action_failed_reply(result["error"])
        )
        label = "execute:ok" if ok else f"execute:{result['error']}"
        return {
            "route": "supervisor",
            "replies": [*state["replies"], reply],
            "outcome": [*state["outcome"], label],
        }

    def finalize(self, state: WorkflowState) -> dict:
        posted = self.post(state, "finalize", state["replies"])
        repository.insert_audit_event(
            self.deps.conn,
            state["patient_id"],
            "workflow",
            "workflow_finished",
            {"thread_id": state["thread_id"], "outcome": state["outcome"]},
            current_trace_id(),
        )
        return posted
