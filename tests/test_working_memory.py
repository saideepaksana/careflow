import json

from careflow.agents.intake import Turn
from careflow.config import CHARS_PER_TOKEN, WORKING_KEEP_TURNS, WORKING_TOKEN_BUDGET
from careflow.llm.gateway import FakeLLM
from careflow.memory.working import (
    SessionSummary,
    WorkingMemory,
    fold_if_needed,
    render_summary,
)

SUMMARY_REPLY = json.dumps(
    {"summary": "Moved cardiology to Friday.", "key_facts": ["Cardiology on Friday"]}
)


def long_turns(count: int) -> list[Turn]:
    size = (WORKING_TOKEN_BUDGET * CHARS_PER_TOKEN) // count + 10
    return [Turn(role="patient", text=f"turn-{index} " + "x" * size) for index in range(count)]


def test_under_budget_makes_no_call() -> None:
    llm = FakeLLM([])
    memory = WorkingMemory(recent=[Turn(role="patient", text="hello")])
    assert fold_if_needed(llm, memory, [1]) == memory
    assert llm.calls == []


def test_over_budget_folds_older_turns() -> None:
    turns = long_turns(10)
    llm = FakeLLM([SUMMARY_REPLY])
    folded = fold_if_needed(llm, WorkingMemory(recent=turns), list(range(101, 111)))
    assert len(llm.calls) == 1
    assert folded.recent == turns[-WORKING_KEEP_TURNS:]
    assert folded.summarized_through == 110 - WORKING_KEEP_TURNS
    assert "turn-0" in llm.calls[0][1]
    assert f"turn-{10 - WORKING_KEEP_TURNS}" not in llm.calls[0][1]


def test_previous_summary_is_in_fold_prompt() -> None:
    previous = SessionSummary(summary="Daughter drives on Mondays.")
    llm = FakeLLM([SUMMARY_REPLY])
    fold_if_needed(llm, WorkingMemory(summary=previous, recent=long_turns(10)), list(range(10)))
    assert "Daughter drives on Mondays." in llm.calls[0][1]


def test_render_summary_lists_key_facts() -> None:
    summary = SessionSummary(summary="s", key_facts=["Fever 38.6", "Prefers mornings"])
    rendered = render_summary(summary)
    assert "- Fever 38.6" in rendered
    assert "- Prefers mornings" in rendered
