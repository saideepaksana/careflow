import json
from typing import Literal

from pydantic import BaseModel, field_validator

from careflow import clock
from careflow.agents.baseline_prompt import (
    BASELINE_SYSTEM_PROMPT,
    FALLBACK_REPLY,
    UNAVAILABLE_REPLY,
)
from careflow.agents.intake import Turn
from careflow.agents.tools import PatientTools
from careflow.config import AGENT_MAX_STEPS, THOUGHT_MAX_CHARS
from careflow.llm.gateway import LLM, LLMOutputError, LLMUnavailableError, complete_structured

StopReason = Literal["replied", "max_steps", "invalid_output", "llm_unavailable"]


class AgentStep(BaseModel):
    thought: str = ""
    action: Literal["call_tool", "reply"]
    tool: str | None = None
    args: dict = {}
    reply: str | None = None

    @field_validator("thought", mode="before")
    @classmethod
    def truncate_thought(cls, value: object) -> object:
        return value[:THOUGHT_MAX_CHARS] if isinstance(value, str) else value


class AgentContext(BaseModel):
    summary: str = ""
    recent: list[Turn] = []
    memories: list[str] = []


class AgentResult(BaseModel):
    reply: str
    stop_reason: StopReason
    tool_calls: list[dict]


def build_agent_prompt(message: str, context: AgentContext, steps: list[dict]) -> str:
    turns = "\n".join(f"{turn.role}: {turn.text}" for turn in context.recent)
    memories = "\n".join(context.memories)
    return (
        f"Today is {clock.today().isoformat()}.\n"
        f"<session_summary>\n{context.summary}\n</session_summary>\n"
        f"<patient_memory>\n{memories}\n</patient_memory>\n"
        f"<conversation>\n{turns}\n</conversation>\n"
        f"<patient_message>\n{message}\n</patient_message>\n"
        f"Steps so far:\n{json.dumps(steps)}"
    )


def is_valid_step(step: AgentStep) -> bool:
    if step.action == "reply":
        return bool(step.reply and step.reply.strip())
    return bool(step.tool)


def next_step(llm: LLM, system: str, prompt: str) -> AgentStep | None:
    try:
        step = complete_structured(llm, system, prompt, AgentStep)
    except LLMOutputError:
        return None
    return step if is_valid_step(step) else None


def run_baseline_agent(
    llm: LLM, tools: PatientTools, message: str, context: AgentContext
) -> AgentResult:
    system = BASELINE_SYSTEM_PROMPT + tools.describe()
    steps: list[dict] = []
    for _ in range(AGENT_MAX_STEPS):
        try:
            step = next_step(llm, system, build_agent_prompt(message, context, steps))
        except LLMUnavailableError:
            return AgentResult(
                reply=UNAVAILABLE_REPLY, stop_reason="llm_unavailable", tool_calls=steps
            )
        if step is None:
            return AgentResult(reply=FALLBACK_REPLY, stop_reason="invalid_output", tool_calls=steps)
        if step.action == "reply":
            return AgentResult(reply=step.reply, stop_reason="replied", tool_calls=steps)
        result = tools.call_tool(step.tool, step.args)
        steps.append(
            {"thought": step.thought, "tool": step.tool, "args": step.args, "result": result}
        )
    return AgentResult(reply=FALLBACK_REPLY, stop_reason="max_steps", tool_calls=steps)
