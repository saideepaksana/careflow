from html import escape

from pydantic import BaseModel

from careflow.config import JUDGE_EVIDENCE_CHUNKS
from careflow.db import repository
from careflow.db.connection import Connection
from careflow.evaluation.judge_prompt import JUDGE_SYSTEM_PROMPT
from careflow.knowledge.rerank import Reranker
from careflow.knowledge.search import RetrievalMode, rank_chunks
from careflow.llm.gateway import LLM, complete_structured
from careflow.memory.embeddings import Embedder

JUDGED_CATEGORIES = ("care_plan_question", "out_of_scope", "explicit_red_flag", "implicit_red_flag")


class Claim(BaseModel):
    text: str
    supported: bool


class Judgement(BaseModel):
    claims: list[Claim] = []


def evidence_ids(
    conn: Connection, embedder: Embedder, reranker: Reranker, patient_id: str, texts: list[str]
) -> list[str]:
    """The union of the top chunks for each text, in first-seen order."""
    ranked = [
        rank_chunks(conn, embedder, reranker, patient_id, text, RetrievalMode.HYBRID_RERANK)
        for text in texts
        if text
    ]
    ids = [chunk_id for ranking in ranked for chunk_id in ranking[:JUDGE_EVIDENCE_CHUNKS]]
    return list(dict.fromkeys(ids))


def build_judge_prompt(question: str, reply: str, chunks: list[dict]) -> str:
    evidence = "\n".join(
        f"[{chunk['title']}, {chunk['heading']}] {escape(chunk['content'], quote=False)}"
        for chunk in chunks
    )
    return (
        f"<question>\n{escape(question, quote=False)}\n</question>\n"
        f"<reply>\n{escape(reply, quote=False)}\n</reply>\n"
        f"<evidence>\n{evidence}\n</evidence>"
    )


def judge_reply(
    llm: LLM,
    conn: Connection,
    embedder: Embedder,
    reranker: Reranker,
    patient_id: str,
    question: str,
    reply: str,
) -> Judgement:
    ids = evidence_ids(conn, embedder, reranker, patient_id, [question, reply])
    prompt = build_judge_prompt(question, reply, repository.get_chunks(conn, ids))
    return complete_structured(llm, JUDGE_SYSTEM_PROMPT, prompt, Judgement)
