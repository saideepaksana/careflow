from pydantic import BaseModel, field_validator

from careflow.agents.intake import Turn
from careflow.config import (
    CHARS_PER_TOKEN,
    KEY_FACTS_MAX,
    MEMORY_VALUE_MAX_CHARS,
    SESSION_SUMMARY_MAX_CHARS,
    WORKING_KEEP_TURNS,
    WORKING_TOKEN_BUDGET,
)
from careflow.llm.gateway import LLM, complete_structured
from careflow.memory.prompts import SUMMARY_SYSTEM_PROMPT


class SessionSummary(BaseModel):
    summary: str
    key_facts: list[str] = []

    @field_validator("summary", mode="before")
    @classmethod
    def truncate_summary(cls, value: object) -> object:
        return value[:SESSION_SUMMARY_MAX_CHARS] if isinstance(value, str) else value

    @field_validator("key_facts", mode="before")
    @classmethod
    def limit_key_facts(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        return [str(fact)[:MEMORY_VALUE_MAX_CHARS] for fact in value[:KEY_FACTS_MAX]]


class WorkingMemory(BaseModel):
    summary: SessionSummary | None = None
    recent: list[Turn] = []
    summarized_through: int = 0


def estimate_tokens(turns: list[Turn]) -> int:
    return sum(len(turn.text) for turn in turns) // CHARS_PER_TOKEN


def format_turns(turns: list[Turn]) -> str:
    return "\n".join(f"{turn.role}: {turn.text}" for turn in turns)


def render_summary(summary: SessionSummary | None) -> str:
    if summary is None:
        return ""
    facts = "\n".join(f"- {fact}" for fact in summary.key_facts)
    return f"{summary.summary}\nKey facts:\n{facts}" if facts else summary.summary


def build_fold_prompt(summary: SessionSummary | None, turns: list[Turn]) -> str:
    return (
        f"<previous_summary>\n{render_summary(summary)}\n</previous_summary>\n"
        f"<turns>\n{format_turns(turns)}\n</turns>"
    )


def fold_if_needed(llm: LLM, memory: WorkingMemory, turn_ids: list[int]) -> WorkingMemory:
    split = len(memory.recent) - WORKING_KEEP_TURNS
    if split <= 0 or estimate_tokens(memory.recent) <= WORKING_TOKEN_BUDGET:
        return memory
    prompt = build_fold_prompt(memory.summary, memory.recent[:split])
    summary = complete_structured(llm, SUMMARY_SYSTEM_PROMPT, prompt, SessionSummary)
    return WorkingMemory(
        summary=summary,
        recent=memory.recent[split:],
        summarized_through=turn_ids[split - 1],
    )
