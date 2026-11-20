import litellm
import pytest
from litellm import ModelResponse
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic import BaseModel

from careflow.config import Settings
from careflow.llm.gateway import (
    FakeLLM,
    LiteLLMClient,
    LLMBudgetExceeded,
    LLMOutputError,
    LLMRejectedError,
    LLMUnavailableError,
    build_llm,
    complete_structured,
)
from careflow.observability.budget import RequestBudget, request_budget

CLIENT_SETTINGS = Settings(llm_model="groq/x", llm_api_key="k")


class Answer(BaseModel):
    value: int


def test_valid_reply_parses_first_time() -> None:
    llm = FakeLLM(['{"value": 3}'])
    assert complete_structured(llm, "sys", "user", Answer).value == 3
    assert len(llm.calls) == 1


def test_code_fenced_json_parses() -> None:
    llm = FakeLLM(['```json\n{"value": 4}\n```'])
    assert complete_structured(llm, "sys", "user", Answer).value == 4


def test_invalid_reply_is_repaired_with_error_feedback() -> None:
    llm = FakeLLM(['{"value": "many"}', '{"value": 5}'])
    assert complete_structured(llm, "sys", "user", Answer).value == 5
    assert "Your previous reply was invalid" in llm.calls[1][1]
    assert "value" in llm.calls[1][1]


def test_repairs_are_capped() -> None:
    llm = FakeLLM(["not json", "still not", "nope"])
    with pytest.raises(LLMOutputError):
        complete_structured(llm, "sys", "user", Answer)
    assert len(llm.calls) == 3


@pytest.mark.parametrize(
    "settings",
    [Settings(llm_model="groq/x"), Settings(llm_api_key="secret")],
)
def test_build_llm_requires_model_and_key(settings: Settings) -> None:
    with pytest.raises(RuntimeError) as error:
        build_llm(settings)
    assert "secret" not in str(error.value)


def test_provider_json_rejection_becomes_empty_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    def reject(**_: object) -> None:
        raise litellm.BadRequestError(
            message='{"error": {"code": "json_validate_failed"}}', model="m", llm_provider="groq"
        )

    monkeypatch.setattr(litellm, "completion", reject)
    assert LiteLLMClient(CLIENT_SETTINGS).complete("system", "user") == ""


@pytest.mark.parametrize(
    "error",
    [
        litellm.BadRequestError(message="context too long", model="m", llm_provider="groq"),
        litellm.ContentPolicyViolationError(message="flagged", model="m", llm_provider="groq"),
        litellm.AuthenticationError(message="bad key", model="m", llm_provider="groq"),
        litellm.APIError(status_code=418, message="odd", model="m", llm_provider="groq"),
    ],
)
def test_rejected_requests_become_unavailable(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    def reject(**_: object) -> None:
        raise error

    monkeypatch.setattr(litellm, "completion", reject)
    with pytest.raises(LLMRejectedError):
        LiteLLMClient(CLIENT_SETTINGS).complete("system", "user")


PRIMARY, FALLBACK = "groq/openai/gpt-oss-120b", "groq/openai/gpt-oss-20b"
FALLBACK_SETTINGS = Settings(llm_model=PRIMARY, llm_fallback_model=FALLBACK, llm_api_key="k")


def reply(model: str, prompt_tokens: int = 1000, completion_tokens: int = 500) -> ModelResponse:
    return ModelResponse(
        model=model.split("/", 1)[1],
        choices=[{"message": {"content": '{"value": 1}', "role": "assistant"}}],
        usage={
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    )


def scripted_provider(failing: set[str], calls: list[str], error: type = litellm.RateLimitError):
    def completion(model: str, **_: object) -> ModelResponse:
        calls.append(model)
        if model in failing:
            raise error(message="no", llm_provider="groq", model=model)
        return reply(model)

    return completion


def client(settings: Settings = FALLBACK_SETTINGS) -> LiteLLMClient:
    return LiteLLMClient(settings, sleep=lambda _: None)


def chat_spans(spans: InMemorySpanExporter) -> list:
    return [s for s in spans.get_finished_spans() if s.name.startswith("chat ")]


def test_usage_and_cost_are_recorded(
    spans: InMemorySpanExporter, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(litellm, "completion", scripted_provider(set(), []))
    with request_budget() as budget:
        client().complete("system", "user")
    [chat] = chat_spans(spans)
    assert chat.attributes["gen_ai.usage.input_tokens"] == 1000
    assert chat.attributes["careflow.cost_usd"] == pytest.approx(0.00045)
    assert chat.attributes["careflow.cost_known"] is True
    assert (budget.input_tokens, budget.output_tokens, budget.llm_calls) == (1000, 500, 1)


def test_unknown_model_costs_nothing(
    spans: InMemorySpanExporter, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(litellm, "completion", scripted_provider(set(), []))
    client(Settings(llm_model="groq/unknown-model", llm_api_key="k")).complete("s", "u")
    [chat] = chat_spans(spans)
    assert (chat.attributes["careflow.cost_usd"], chat.attributes["careflow.cost_known"]) == (
        0.0,
        False,
    )


@pytest.mark.parametrize(
    "error",
    [
        litellm.RateLimitError,
        litellm.BadGatewayError,
        litellm.NotFoundError,
        litellm.BadRequestError,
    ],
)
def test_fallback_answers_when_primary_fails(
    spans: InMemorySpanExporter, monkeypatch: pytest.MonkeyPatch, error: type
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(litellm, "completion", scripted_provider({PRIMARY}, calls, error))
    assert client().complete("system", "user") == '{"value": 1}'
    assert calls[-1] == FALLBACK
    assert [s.attributes["careflow.fallback"] for s in chat_spans(spans)] == [False, True]


def test_open_primary_breaker_does_not_block_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(litellm, "completion", scripted_provider(set(), calls))
    gateway = client()
    gateway.breakers[PRIMARY].opened_at = gateway.breakers[PRIMARY].clock()
    gateway.complete("system", "user")
    assert calls == [FALLBACK]


def test_both_models_failing_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(litellm, "completion", scripted_provider({PRIMARY, FALLBACK}, []))
    with pytest.raises(LLMUnavailableError) as error:
        client().complete("system", "user")
    assert not isinstance(error.value, LLMRejectedError)


def test_spent_budget_stops_before_calling_any_model(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(litellm, "completion", scripted_provider(set(), calls))
    with request_budget(RequestBudget(max_tokens=0)), pytest.raises(LLMBudgetExceeded):
        client().complete("system", "user")
    assert calls == []


@pytest.mark.parametrize("status", [498, 500, 520])
def test_unmapped_capacity_and_server_errors_are_outages(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    def overloaded(**_: object) -> None:
        raise litellm.APIError(status_code=status, message="busy", model="m", llm_provider="groq")

    monkeypatch.setattr(litellm, "completion", overloaded)
    with pytest.raises(LLMUnavailableError) as error:
        LiteLLMClient(CLIENT_SETTINGS, sleep=lambda _: None).complete("system", "user")
    assert not isinstance(error.value, LLMRejectedError)
