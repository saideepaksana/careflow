from typing import TypedDict


class WorkflowState(TypedDict, total=False):
    """Checkpointed workflow state; every value is JSON-compatible."""

    patient_id: str
    conversation_id: str
    thread_id: str
    message: str
    recent: list[dict]
    summary: str
    memories: list[str]
    intake: dict | None
    gate: dict | None
    pending: list[int] | None
    current: int | None
    steps: int
    route: str
    handoff_reason: str
    replies: list[str]
    visits: dict[str, int]
    plan: dict | None
    verdict: dict | None
    replans: int
    feedback: str
    coordinator_approved: bool
    outcome: list[str]
