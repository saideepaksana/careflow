from typing import Protocol

from fastembed.rerank.cross_encoder import TextCrossEncoder

from careflow.config import MODEL_CACHE_DIR, RERANKER_MODEL


class Reranker(Protocol):
    def score(self, query: str, texts: list[str]) -> list[float]: ...


class FastReranker:
    def __init__(self) -> None:
        self.model: TextCrossEncoder | None = None

    def score(self, query: str, texts: list[str]) -> list[float]:
        if self.model is None:
            self.model = TextCrossEncoder(RERANKER_MODEL, cache_dir=str(MODEL_CACHE_DIR))
        return [float(value) for value in self.model.rerank(query, texts)]


class FakeReranker:
    """Scores by shared lower-case words, for tests."""

    def score(self, query: str, texts: list[str]) -> list[float]:
        words = set(query.lower().split())
        return [float(len(words & set(text.lower().split()))) for text in texts]
