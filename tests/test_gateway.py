import litellm
import pytest
from pydantic import BaseModel

from careflow.config import Settings
from careflow.llm.gateway import (
    FakeLLM,
    LiteLLMClient,
    LLMOutputError,
    build_llm,
    complete_structured,
)

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
    assert LiteLLMClient(CLIENT_SETTINGS).send("system", "user") == ""


def test_other_bad_requests_still_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    def reject(**_: object) -> None:
        raise litellm.BadRequestError(message="model not found", model="m", llm_provider="groq")

    monkeypatch.setattr(litellm, "completion", reject)
    with pytest.raises(litellm.BadRequestError):
        LiteLLMClient(CLIENT_SETTINGS).send("system", "user")
