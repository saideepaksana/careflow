import time
from dataclasses import dataclass, replace

from careflow.config import Settings
from careflow.db import repository
from careflow.db.connection import connect
from careflow.evaluation.scenarios import (
    PRIORITY_RANK,
    Observation,
    Scenario,
    Step,
    StepResult,
    check_scenario,
    completes_after_approval,
    missing_item_link,
)
from careflow.evaluation.systems import BaselineSystem, CareFlowSystem, RecordingLLM
from careflow.knowledge.rerank import Reranker
from careflow.memory.embeddings import Embedder
from careflow.observability.meter import UsageMeter

SYSTEMS = {"careflow": CareFlowSystem, "baseline": BaselineSystem}


@dataclass
class CellContext:
    settings: Settings
    llm: RecordingLLM
    embedder: Embedder
    reranker: Reranker
    meter: UsageMeter


def run_step(system: object, step: Step) -> tuple[list[str], bool]:
    value = getattr(step, step.kind)
    action = getattr(system, step.kind)
    try:
        return action() if step.kind == "end_session" else action(value)
    except Exception as error:  # evaluation runner boundary: a system error is a scored failure
        return [f"error:{type(error).__name__}"], False


def observe_step(ctx: CellContext, system: object, step: Step, patient_id: str) -> StepResult:
    with connect(ctx.settings.database_url) as conn:
        before = repository.appointment_snapshot(conn, patient_id)
        tasks_before = len(repository.task_snapshot(conn, patient_id))
    throttled, started = ctx.llm.throttled_seconds, time.monotonic()
    replies, noop = run_step(system, step)
    wall = time.monotonic() - started
    throttle = ctx.llm.throttled_seconds - throttled
    with connect(ctx.settings.database_url) as conn:
        after = repository.appointment_snapshot(conn, patient_id)
        tasks = repository.task_snapshot(conn, patient_id)[tasks_before:]
    changed = [key for key, row in after.items() if before.get(key) != row]
    return StepResult(
        kind=step.kind,
        replies=replies,
        noop=noop,
        wall_ms=round((wall - throttle) * 1000),
        throttle_ms=round(throttle * 1000),
        usage=ctx.meter.take(),
        changed=changed,
        tasks=[{"priority": t["priority"], "kind": t["kind"]} for t in tasks],
    )


def run_cell(ctx: CellContext, scenario: Scenario, system_name: str) -> dict:
    """Run one scenario on one system against a freshly cloned evaluation database."""
    with connect(ctx.settings.database_url) as conn:
        initial = repository.appointment_snapshot(conn, scenario.patient_id)
    ctx.meter.take()
    unavailable = ctx.llm.unavailable
    system = SYSTEMS[system_name](
        ctx.settings, ctx.llm, ctx.embedder, ctx.reranker, scenario.patient_id
    )
    try:
        steps = [observe_step(ctx, system, step, scenario.patient_id) for step in scenario.steps]
    finally:
        system.close()
    with connect(ctx.settings.database_url) as conn:
        final = repository.appointment_snapshot(conn, scenario.patient_id)
        tasks = repository.task_snapshot(conn, scenario.patient_id)
    observation = Observation(steps=steps, initial=initial, final=final, tasks=tasks)
    return cell_row(ctx, scenario, observation, ctx.llm.unavailable > unavailable)


def cell_row(ctx: CellContext, scenario: Scenario, observation: Observation, outage: bool) -> dict:
    other_model = bool(
        {c["model"] for s in observation.steps for c in s.usage} - {ctx.settings.llm_model}
    )
    failed = check_scenario(scenario, observation)
    question = next((s.say for s in reversed(scenario.steps) if s.say), "")
    reason = "provider_unavailable" if outage else ("other_model" if other_model else "")
    return {
        "valid": not reason,
        "invalid_reason": reason,
        "success": not failed,
        "failed_checks": failed,
        "completes_after_approval": completes_after_approval(scenario, observation),
        "missing_item_link": missing_item_link(scenario, observation),
        "escalation": max(
            (t["priority"] for t in observation.tasks), key=PRIORITY_RANK.get, default=None
        ),
        "question": question,
        "final_reply": replies_after_last_say(observation),
        "steps": [step.model_dump(mode="json") for step in observation.steps],
    }


def replies_after_last_say(observation: Observation) -> str:
    kinds = [step.kind for step in observation.steps]
    if "say" not in kinds:
        return ""
    last_say = len(kinds) - 1 - kinds[::-1].index("say")
    return " ".join(r for step in observation.steps[last_say:] for r in step.replies)


def eval_settings(settings: Settings, database_url: str) -> Settings:
    return replace(settings, database_url=database_url, llm_fallback_model="")
