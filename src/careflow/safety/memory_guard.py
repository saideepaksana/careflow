import re

from careflow.config import CLINICAL_TERMS

CLINICAL_PATTERN = re.compile(r"\b(" + "|".join(re.escape(term) for term in CLINICAL_TERMS) + ")")


def is_clinical(text: str) -> bool:
    return CLINICAL_PATTERN.search(text.lower()) is not None
