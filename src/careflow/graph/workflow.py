import uuid
from collections.abc import Callable

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from pydantic import BaseModel

from careflow.agents.intake import Turn
from careflow.db import repository
from careflow.graph.nodes import LLM_ERRORS, WorkflowDeps, WorkflowNodes
from careflow.graph.state import WorkflowState

Crash = Callable[[str], None]
Checkpointer = BaseCheckpointSaver
DURABILITY = "sync"
ROUTES = {
    "safety_gate": ["escalate", "supervisor"],
    "supervisor": ["answer_question", "plan_schedule", "hand_off", "finalize"],
    "plan_schedule": ["verify", "hand_off"],
    "verify": ["ask_confirmation", "plan_schedule", "hand_off", "supervisor"],
    "ask_confirmation": ["await_coordinator", "execute", "supervisor"],
    "await_coordinator": ["execute", "finalize"],
}
FIXED_EDGES = (
    (START, "intake"),
    ("intake", "safety_gate"),
    ("escalate", "finalize"),
    ("answer_question", "supervisor"),
    ("hand_off", "supervisor"),
    ("execute", "supervisor"),
    ("finalize", END),
)
NODE_NAMES = (
    "intake",
    "safety_gate",
    "escalate",
    "supervisor",
    "answer_question",
    "hand_off",
    "plan_schedule",
    "verify",
    "ask_confirmation",
    "await_coordinator",
    "execute",
    "finalize",
)


class NoPendingInterrupt(Exception):
    pass


class RunResult(BaseModel):
    thread_id: str
    status: str
    messages: list[str]
    confirmation: str | None = None


class RunContext(BaseModel):
    summary: str = ""
    recent: list[Turn] = []
    memories: list[str] = []


def with_crash_points(name: str, node: Callable, crash: Crash | None) -> Callable:
    if crash is None:
        return node

    def wrapped(state: WorkflowState) -> dict:
        crash(f"before:{name}")
        update = node(state)
        crash(f"after:{name}")
        return update

    return wrapped


def build_graph(
    deps: WorkflowDeps, checkpointer: BaseCheckpointSaver, crash: Crash | None = None
) -> CompiledStateGraph:
    nodes = WorkflowNodes(deps)
    graph = StateGraph(WorkflowState)
    for name in NODE_NAMES:
        graph.add_node(name, with_crash_points(name, getattr(nodes, name), crash))
    for source, target in FIXED_EDGES:
        graph.add_edge(source, target)
    for source, targets in ROUTES.items():
        graph.add_conditional_edges(source, lambda state: state["route"], targets)
    return graph.compile(checkpointer=checkpointer)


def thread_config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def initial_state(
    thread_id: str, conversation_id: str, patient_id: str, message: str, context: RunContext
) -> WorkflowState:
    return {
        "patient_id": patient_id,
        "conversation_id": conversation_id,
        "thread_id": thread_id,
        "message": message,
        "recent": [turn.model_dump() for turn in context.recent],
        "summary": context.summary,
        "memories": context.memories,
        "intake": None,
        "pending": None,
        "current": None,
        "steps": 0,
        "replies": [],
        "visits": {},
        "replans": 0,
        "feedback": "",
        "coordinator_approved": False,
        "outcome": [],
    }


def finish(
    deps: WorkflowDeps, graph: CompiledStateGraph, thread_id: str, after_message: int
) -> RunResult:
    run = repository.get_run(deps.conn, thread_id)
    interrupts = graph.get_state(thread_config(thread_id)).interrupts
    payload = interrupts[0].value if interrupts else {}
    status = f"awaiting_{payload['kind']}" if interrupts else "done"
    repository.set_run_status(deps.conn, thread_id, status)
    messages = repository.assistant_messages_after(deps.conn, run["conversation_id"], after_message)
    return RunResult(
        thread_id=thread_id,
        status=status,
        messages=messages,
        confirmation=payload.get("summary") if payload.get("kind") == "confirmation" else None,
    )


def start_run(
    deps: WorkflowDeps,
    checkpointer: BaseCheckpointSaver,
    conversation_id: str,
    patient_id: str,
    message: str,
    context: RunContext,
    crash: Crash | None = None,
) -> RunResult:
    thread_id = f"{conversation_id}:{uuid.uuid4().hex[:8]}"
    repository.create_workflow_run(deps.conn, thread_id, conversation_id)
    after_message = repository.last_message_id(deps.conn, conversation_id)
    graph = build_graph(deps, checkpointer, crash)
    state = initial_state(thread_id, conversation_id, patient_id, message, context)
    graph.invoke(state, thread_config(thread_id), durability=DURABILITY)
    return finish(deps, graph, thread_id, after_message)


def resume_run(
    deps: WorkflowDeps,
    checkpointer: BaseCheckpointSaver,
    thread_id: str,
    kind: str,
    value: object,
    crash: Crash | None = None,
) -> RunResult:
    graph = build_graph(deps, checkpointer, crash)
    config = thread_config(thread_id)
    interrupts = graph.get_state(config).interrupts
    if len(interrupts) != 1 or interrupts[0].value.get("kind") != kind:
        raise NoPendingInterrupt(thread_id)
    run = repository.get_run(deps.conn, thread_id)
    after_message = repository.last_message_id(deps.conn, run["conversation_id"])
    repository.set_run_status(deps.conn, thread_id, "running")
    graph.invoke(Command(resume={interrupts[0].id: value}), config, durability=DURABILITY)
    return finish(deps, graph, thread_id, after_message)


def recover_run(
    deps: WorkflowDeps,
    checkpointer: BaseCheckpointSaver,
    thread_id: str,
    crash: Crash | None = None,
) -> RunResult:
    """Continue a run that a crash left in status running."""
    graph = build_graph(deps, checkpointer, crash)
    config = thread_config(thread_id)
    run = repository.get_run(deps.conn, thread_id)
    after_message = repository.last_message_id(deps.conn, run["conversation_id"])
    failed = RunResult(thread_id=thread_id, status="failed", messages=[])
    if not graph.get_state(config).values:
        repository.set_run_status(deps.conn, thread_id, "failed")
        return failed
    try:
        graph.invoke(None, config, durability=DURABILITY)
    except LLM_ERRORS:
        repository.set_run_status(deps.conn, thread_id, "failed")
        return failed
    return finish(deps, graph, thread_id, after_message)
