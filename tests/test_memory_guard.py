import pytest

from careflow.safety.memory_guard import is_clinical, without_clinical_sentences


@pytest.mark.parametrize(
    "text",
    [
        "takes metformin 500 mg",
        "stopped her medication",
        "allergic to penicillin",
        "has ankle swelling",
        "weight went up",
        "Blood pressure runs high",
        "takes metformin 500mg twice daily",
        "prefers 10mg",
        "usually 2 units at night",
        "BP 160/100",
        "BP 98/60",
        "I stopped taking metoprolol",
        "on warfarin",
        "has heart failure",
        "takes two pills at night",
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
        "next visit on 12/11",
        "prefers Dr. Meena Pillai",
    ],
)
def test_non_clinical_text_passes(text: str) -> None:
    assert not is_clinical(text)


@pytest.mark.parametrize(
    ("text", "kept"),
    [
        (
            "Booked the lab. Takes 500mg metformin. Prefers mornings.",
            "Booked the lab. Prefers mornings.",
        ),
        ("Asked when the visit is.", "Asked when the visit is."),
        ("Reported ankle swelling.", ""),
    ],
)
def test_clinical_sentences_are_removed(text: str, kept: str) -> None:
    assert without_clinical_sentences(text) == kept
