import re

from careflow.config import CLINICAL_TERMS

CLINICAL_PATTERN = re.compile(r"\b(" + "|".join(re.escape(term) for term in CLINICAL_TERMS) + ")")
DOSE_PATTERN = re.compile(r"\d\s*(mg|mcg|ml|units?)\b")
READING_PATTERN = re.compile(r"\b\d{3}\s*/\s*\d{2,3}\b")
WORD_PATTERN = re.compile(r"\b(pills?|bp)\b")
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def is_clinical(text: str) -> bool:
    lowered = text.lower()
    return any(
        pattern.search(lowered) is not None
        for pattern in (CLINICAL_PATTERN, DOSE_PATTERN, READING_PATTERN, WORD_PATTERN)
    )


def without_clinical_sentences(text: str) -> str:
    """Keep only the sentences of a session summary that carry no clinical detail."""
    return " ".join(part for part in SENTENCE_END.split(text.strip()) if not is_clinical(part))
