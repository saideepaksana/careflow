import pytest
from pydantic import BaseModel

from careflow.config import Settings
from careflow.llm.gateway import FakeLLM, LLMOutputError, build_llm, complete_structured


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
