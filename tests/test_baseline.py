import json

from careflow.agents.baseline import run_baseline_agent
from careflow.agents.baseline_prompt import FALLBACK_REPLY, UNAVAILABLE_REPLY
from careflow.config import AGENT_MAX_STEPS
from careflow.llm.gateway import FakeLLM, LLMUnavailableError


class StubTools:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def describe(self) -> str:
        return "- list_appointments: List appointments."

    def call_tool(self, name: str, args: dict) -> dict:
        self.calls.append((name, args))
        return {"ok": True, "data": ["A001 on 2026-11-11"]}


class DownLLM:
    def complete(self, system: str, user: str) -> str:
        raise LLMUnavailableError("RateLimitError")


def reply(text: str) -> str:
    return json.dumps({"action": "reply", "reply": text})


def tool_call(name: str) -> str:
    return json.dumps({"action": "call_tool", "tool": name, "args": {}})


def test_direct_reply() -> None:
    result = run_baseline_agent(FakeLLM([reply("Hello")]), StubTools(), "hi", [])
    assert result.reply == "Hello"
    assert result.stop_reason == "replied"


def test_tool_result_reaches_next_prompt() -> None:
    llm = FakeLLM([tool_call("list_appointments"), reply("You have one visit.")])
    tools = StubTools()
    result = run_baseline_agent(llm, tools, "what visits do I have?", [])
    assert tools.calls == [("list_appointments", {})]
    assert "A001 on 2026-11-11" in llm.calls[1][1]
    assert result.tool_calls[0]["tool"] == "list_appointments"


def test_step_cap_stops_loop() -> None:
    llm = FakeLLM([tool_call("list_appointments")] * AGENT_MAX_STEPS)
    result = run_baseline_agent(llm, StubTools(), "loop", [])
    assert result.stop_reason == "max_steps"
    assert result.reply == FALLBACK_REPLY
    assert len(llm.calls) == AGENT_MAX_STEPS


def test_invalid_output_falls_back() -> None:
    llm = FakeLLM([json.dumps({"action": "reply"})] * 3)
    result = run_baseline_agent(llm, StubTools(), "hi", [])
    assert result.stop_reason == "invalid_output"
    assert result.reply == FALLBACK_REPLY


def test_unavailable_llm_gives_template() -> None:
    result = run_baseline_agent(DownLLM(), StubTools(), "hi", [])
    assert result.stop_reason == "llm_unavailable"
    assert result.reply == UNAVAILABLE_REPLY
