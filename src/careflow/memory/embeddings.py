import hashlib
import math
from typing import Protocol

from fastembed import TextEmbedding

from careflow.config import EMBEDDING_DIM, EMBEDDING_MODEL, MODEL_CACHE_DIR


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


def normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


class FastEmbedder:
    def __init__(self) -> None:
        self.model: TextEmbedding | None = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self.model is None:
            self.model = TextEmbedding(EMBEDDING_MODEL, cache_dir=str(MODEL_CACHE_DIR))
        return [normalize(vector.tolist()) for vector in self.model.embed(texts)]


class FakeEmbedder:
    """Deterministic bag-of-words embedding for tests."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_one(text) for text in texts]

    def embed_one(self, text: str) -> list[float]:
        vector = [0.0] * EMBEDDING_DIM
        for word in text.lower().split():
            bucket = int(hashlib.sha256(word.encode()).hexdigest(), 16) % EMBEDDING_DIM
            vector[bucket] += 1.0
        return normalize(vector)
