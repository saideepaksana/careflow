import pytest

from careflow.safety.memory_guard import is_clinical


@pytest.mark.parametrize(
    "text",
    [
        "takes metformin 500 mg",
        "stopped her medication",
        "allergic to penicillin",
        "has ankle swelling",
        "weight went up",
        "Blood pressure runs high",
    ],
)
def test_clinical_text_is_flagged(text: str) -> None:
    assert is_clinical(text)


@pytest.mark.parametrize(
    "text",
    [
        "prefers mornings",
        "daughter Priya drives on Mondays",
        "call after 5 pm",
        "uses a wheelchair",
        "Dr. Anil Verma",
    ],
)
def test_non_clinical_text_passes(text: str) -> None:
    assert not is_clinical(text)
