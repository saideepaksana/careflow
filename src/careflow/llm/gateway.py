import json
import time
from collections.abc import Callable
from typing import Protocol, TypeVar

import litellm
from pydantic import BaseModel, ValidationError

from careflow.config import LLM_TIMEOUT_SECONDS, MAX_REPAIRS, REPAIR_ERROR_MAX_CHARS, Settings
from careflow.llm.reliability import CircuitBreaker, CircuitOpenError, call_with_retry
from careflow.observability.budget import RequestBudget, current_budget
from careflow.observability.tracing import Span, span

T = TypeVar("T", bound=BaseModel)

litellm.suppress_debug_info = True

TRANSIENT_ERRORS = (
    litellm.RateLimitError,
    litellm.APIConnectionError,
    litellm.Timeout,
    litellm.InternalServerError,
    litellm.ServiceUnavailableError,
)
FALLBACK_ERRORS = (*TRANSIENT_ERRORS, CircuitOpenError, litellm.NotFoundError)
JSON_VALIDATE_FAILED = "json_validate_failed"


class LLM(Protocol):
    def complete(self, system: str, user: str) -> str: ...


class LLMOutputError(Exception):
    pass


class LLMUnavailableError(Exception):
    pass


class LLMBudgetExceeded(LLMUnavailableError):
    pass


def provider_name(model: str) -> str:
    return model.split("/", 1)[0]


def response_cost(model: str, input_tokens: int, output_tokens: int) -> float | None:
    prices = litellm.model_cost.get(model)
    if not prices:
        return None
    return input_tokens * prices.get("input_cost_per_token", 0.0) + output_tokens * prices.get(
        "output_cost_per_token", 0.0
    )


def response_usage(response: object) -> tuple[int, int]:
    usage = getattr(response, "usage", None)
    return (getattr(usage, "prompt_tokens", 0) or 0, getattr(usage, "completion_tokens", 0) or 0)


class LiteLLMClient:
    def __init__(
        self,
        settings: Settings,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.settings = settings
        self.sleep = sleep
        models = [settings.llm_model, settings.llm_fallback_model]
        self.models = [model for model in models if model]
        self.breakers = {model: CircuitBreaker(TRANSIENT_ERRORS, clock) for model in self.models}

    def complete(self, system: str, user: str) -> str:
        for model in self.models:
            try:
                return self.complete_with(model, system, user)
            except FALLBACK_ERRORS:
                continue
        raise LLMUnavailableError("all models failed")

    def complete_with(self, model: str, system: str, user: str) -> str:
        attributes = {
            "gen_ai.operation.name": "chat",
            "gen_ai.provider.name": provider_name(model),
            "gen_ai.request.model": model,
            "careflow.fallback": model != self.settings.llm_model,
        }
        with span(f"chat {model}", **attributes) as current:

            def attempt() -> str:
                return self.send(model, system, user, current)

            return self.breakers[model].call(
                lambda: call_with_retry(attempt, TRANSIENT_ERRORS, self.sleep)
            )

    def send(self, model: str, system: str, user: str, current: Span) -> str:
        budget = current_budget()
        if budget is not None and budget.exceeded():
            raise LLMBudgetExceeded("request budget exhausted")
        timeout = LLM_TIMEOUT_SECONDS
        if budget is not None:
            timeout = min(timeout, budget.remaining_seconds())
        try:
            response = self.request(model, system, user, timeout)
        except litellm.BadRequestError as exc:
            # The provider rejects invalid JSON itself; an empty reply lets the repair loop retry.
            if JSON_VALIDATE_FAILED in str(exc):
                return ""
            raise
        record_usage(model, response, current, budget)
        return response.choices[0].message.content or ""

    def request(self, model: str, system: str, user: str, timeout: float) -> litellm.ModelResponse:
        return litellm.completion(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=self.settings.llm_temperature,
            api_key=self.settings.llm_api_key,
            api_base=self.settings.llm_base_url or None,
            timeout=timeout,
            response_format={"type": "json_object"},
        )


def record_usage(model: str, response: object, current: Span, budget: RequestBudget | None) -> None:
    input_tokens, output_tokens = response_usage(response)
    cost = response_cost(model, input_tokens, output_tokens)
    current.set_attribute("gen_ai.response.model", str(getattr(response, "model", "")))
    current.set_attribute("gen_ai.usage.input_tokens", input_tokens)
    current.set_attribute("gen_ai.usage.output_tokens", output_tokens)
    current.set_attribute("careflow.cost_usd", cost or 0.0)
    current.set_attribute("careflow.cost_known", cost is not None)
    if budget is not None:
        budget.record(input_tokens, output_tokens, cost or 0.0)


class FakeLLM:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if not self.responses:
            raise AssertionError("FakeLLM responses exhausted")
        return self.responses.pop(0)


def parse_json_object(raw: str, schema: type[T]) -> T:
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no JSON object found")
    return schema.model_validate(json.loads(raw[start : end + 1]))


def complete_structured(llm: LLM, system: str, user: str, schema: type[T]) -> T:
    prompt = user
    error = ""
    for _ in range(MAX_REPAIRS + 1):
        try:
            return parse_json_object(llm.complete(system, prompt), schema)
        except (ValueError, ValidationError) as exc:
            error = str(exc)[:REPAIR_ERROR_MAX_CHARS]
            prompt = (
                f"{user}\n\nYour previous reply was invalid: {error}. "
                "Return only the corrected JSON object."
            )
    raise LLMOutputError(error)


def build_llm(settings: Settings) -> LLM:
    if not settings.llm_model or not settings.llm_api_key:
        raise RuntimeError("LLM_MODEL and LLM_API_KEY must be set")
    return LiteLLMClient(settings)
