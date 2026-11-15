from html import escape
from typing import Literal

from pydantic import BaseModel, field_validator

from careflow.agents.careplan_prompt import CAREPLAN_SYSTEM_PROMPT, HANDOFF_REPLY
from careflow.config import ANSWER_SENTENCE_MAX_CHARS, ANSWER_SENTENCES_MAX
from careflow.knowledge.search import RetrievedChunk
from careflow.llm.gateway import LLM, LLMOutputError, LLMUnavailableError, complete_structured


class CitedSentence(BaseModel):
    text: str
    sources: list[str] = []

    @field_validator("text", mode="before")
    @classmethod
    def truncate_text(cls, value: object) -> object:
        return value[:ANSWER_SENTENCE_MAX_CHARS] if isinstance(value, str) else value


class CarePlanAnswer(BaseModel):
    covered: bool
    sentences: list[CitedSentence] = []

    @field_validator("sentences", mode="before")
    @classmethod
    def limit_sentences(cls, value: object) -> object:
        return value[:ANSWER_SENTENCES_MAX] if isinstance(value, list) else value


HandoffReason = Literal["no_sources", "llm_failed", "not_covered", "failed_citation_check"]


class CarePlanResult(BaseModel):
    reply: str
    handed_off: bool
    handoff_reason: HandoffReason | None = None
    cited_chunk_ids: list[str] = []


def source_label(index: int) -> str:
    return f"S{index}"


def build_careplan_prompt(question: str, chunks: list[RetrievedChunk]) -> str:
    sources = "\n".join(
        f'<source label="{source_label(index)}" title="{escape(chunk.title)}"'
        f' section="{escape(chunk.heading)}">\n{escape(chunk.content, quote=False)}\n</source>'
        for index, chunk in enumerate(chunks, start=1)
    )
    return f"{sources}\n<question>\n{escape(question, quote=False)}\n</question>"


def check_citations(answer: CarePlanAnswer, labels: set[str]) -> bool:
    if not answer.covered or not answer.sentences:
        return False
    return all(
        sentence.sources and set(sentence.sources) <= labels for sentence in answer.sentences
    )


def render_sentence(sentence: CitedSentence, by_label: dict[str, RetrievedChunk]) -> str:
    sources = "; ".join(
        f"{by_label[label].title}, {by_label[label].heading}" for label in sentence.sources
    )
    return f"{sentence.text.strip()} [{sources}]"


def handoff(reason: HandoffReason) -> CarePlanResult:
    return CarePlanResult(reply=HANDOFF_REPLY, handed_off=True, handoff_reason=reason)


def answer_question(llm: LLM, question: str, chunks: list[RetrievedChunk]) -> CarePlanResult:
    if not chunks:
        return handoff("no_sources")
    by_label = {source_label(index): chunk for index, chunk in enumerate(chunks, start=1)}
    prompt = build_careplan_prompt(question, chunks)
    try:
        answer = complete_structured(llm, CAREPLAN_SYSTEM_PROMPT, prompt, CarePlanAnswer)
    except (LLMOutputError, LLMUnavailableError):
        return handoff("llm_failed")
    if not answer.covered:
        return handoff("not_covered")
    if not check_citations(answer, set(by_label)):
        return handoff("failed_citation_check")
    cited = dict.fromkeys(label for s in answer.sentences for label in s.sources)
    return CarePlanResult(
        reply=" ".join(render_sentence(s, by_label) for s in answer.sentences),
        handed_off=False,
        cited_chunk_ids=[by_label[label].id for label in cited],
    )
