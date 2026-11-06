import json
from typing import Protocol, TypeVar

import litellm
from pydantic import BaseModel, ValidationError

from careflow.config import LLM_TIMEOUT_SECONDS, MAX_REPAIRS, REPAIR_ERROR_MAX_CHARS, Settings

T = TypeVar("T", bound=BaseModel)


class LLM(Protocol):
    def complete(self, system: str, user: str) -> str: ...


class LLMOutputError(Exception):
    pass


class LiteLLMClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def complete(self, system: str, user: str) -> str:
        response = litellm.completion(
            model=self.settings.llm_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=self.settings.llm_temperature,
            api_key=self.settings.llm_api_key,
            api_base=self.settings.llm_base_url or None,
            timeout=LLM_TIMEOUT_SECONDS,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content or ""


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
