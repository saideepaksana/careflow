import re
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from careflow.config import CHUNK_MAX_CHARS
from careflow.db import repository
from careflow.db.connection import Connection
from careflow.memory.embeddings import Embedder

FRONT_MATTER = "---"
SECTION_PREFIX = "## "
SHARED_OWNER = "shared"


class DocumentMeta(BaseModel):
    id: str
    title: str
    owner: str
    condition: Literal["heart_failure", "copd", "diabetes", "hip_replacement", "pneumonia", "any"]
    version: int
    status: Literal["current", "superseded"]
    effective_from: date


class Chunk(BaseModel):
    id: str
    document_id: str
    heading: str
    content: str


def parse_document(text: str) -> tuple[DocumentMeta, str]:
    lines = text.strip().splitlines()
    if not lines or lines[0] != FRONT_MATTER or FRONT_MATTER not in lines[1:]:
        raise ValueError("document must start with a front-matter block")
    end = lines.index(FRONT_MATTER, 1)
    fields = dict(line.split(":", 1) for line in lines[1:end])
    meta = DocumentMeta.model_validate(
        {key.strip(): value.strip() for key, value in fields.items()}
    )
    return meta, "\n".join(lines[end + 1 :])


def slugify(heading: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")


def split_sections(body: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, list[str]]] = []
    for line in body.splitlines():
        if line.startswith(SECTION_PREFIX):
            sections.append((line.removeprefix(SECTION_PREFIX).strip(), []))
        elif sections:
            sections[-1][1].append(line)
    return [(heading, "\n".join(lines).strip()) for heading, lines in sections]


def split_paragraphs(content: str) -> list[str]:
    parts: list[str] = []
    for paragraph in content.split("\n\n"):
        if parts and len(parts[-1]) + len(paragraph) + 2 <= CHUNK_MAX_CHARS:
            parts[-1] = f"{parts[-1]}\n\n{paragraph}"
        else:
            parts.append(paragraph)
    return parts


def chunk_document(meta: DocumentMeta, body: str) -> list[Chunk]:
    chunks = []
    for heading, content in split_sections(body):
        slug = slugify(heading)
        for index, part in enumerate(split_paragraphs(content), start=1):
            suffix = "" if index == 1 else f"-{index}"
            chunk_id = f"{meta.id}#{slug}{suffix}"
            chunks.append(Chunk(id=chunk_id, document_id=meta.id, heading=heading, content=part))
    return chunks


def load_corpus(corpus_dir: Path) -> list[tuple[DocumentMeta, list[Chunk]]]:
    documents = []
    for path in sorted(corpus_dir.rglob("*.md")):
        meta, body = parse_document(path.read_text())
        documents.append((meta, chunk_document(meta, body)))
    return documents


def embedding_text(meta: DocumentMeta, chunk: Chunk) -> str:
    return f"{meta.title}: {chunk.heading}\n{chunk.content}"


def ingest_corpus(conn: Connection, embedder: Embedder, corpus_dir: Path) -> int:
    corpus = load_corpus(corpus_dir)
    pairs = [(meta, chunk) for meta, chunks in corpus for chunk in chunks]
    embeddings = embedder.embed([embedding_text(meta, chunk) for meta, chunk in pairs])
    documents = [
        {
            **meta.model_dump(exclude={"owner"}),
            "owner_patient_id": None if meta.owner == SHARED_OWNER else meta.owner,
        }
        for meta, _ in corpus
    ]
    chunks = [
        {**chunk.model_dump(), "embedding": embedding}
        for (_, chunk), embedding in zip(pairs, embeddings, strict=True)
    ]
    repository.replace_corpus(conn, documents, chunks)
    return len(chunks)
