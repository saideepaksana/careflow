import pytest

from careflow.config import CHUNK_MAX_CHARS, CORPUS_DIR
from careflow.knowledge.corpus import chunk_document, load_corpus, parse_document

HEADER = """---
id: DOC-1
title: Test plan
owner: P001
condition: heart_failure
version: 2
status: current
effective_from: 2026-10-30
---
"""


def test_front_matter_parses() -> None:
    meta, body = parse_document(HEADER + "\n## Fluids\n\nDrink less.")
    assert (meta.id, meta.owner, meta.version, meta.status) == ("DOC-1", "P001", 2, "current")
    assert body.strip() == "## Fluids\n\nDrink less."


@pytest.mark.parametrize(
    "text",
    [
        "## Fluids\n\nNo front matter.",
        HEADER.replace("title: Test plan\n", ""),
        HEADER.replace("status: current", "status: draft"),
    ],
)
def test_invalid_front_matter_raises(text: str) -> None:
    with pytest.raises(ValueError):
        parse_document(text)


def test_chunks_split_at_sections_with_slug_ids() -> None:
    meta, body = parse_document(
        HEADER + "Intro.\n\n## Fluids and salt\n\nA.\n\n## Follow-up visits\n\nB."
    )
    chunks = chunk_document(meta, body)
    assert [chunk.id for chunk in chunks] == ["DOC-1#fluids-and-salt", "DOC-1#follow-up-visits"]
    assert [chunk.content for chunk in chunks] == ["A.", "B."]


def test_long_section_splits_at_paragraphs() -> None:
    paragraph = "word " * (CHUNK_MAX_CHARS // 15)
    meta, body = parse_document(HEADER + f"## Long\n\n{paragraph}\n\n{paragraph}\n\n{paragraph}")
    chunks = chunk_document(meta, body)
    assert [chunk.id for chunk in chunks] == ["DOC-1#long", "DOC-1#long-2"]
    assert all(len(chunk.content) <= CHUNK_MAX_CHARS for chunk in chunks)


def test_corpus_parses_with_unique_chunk_ids() -> None:
    ids = [chunk.id for _, chunks in load_corpus(CORPUS_DIR) for chunk in chunks]
    assert ids
    assert len(ids) == len(set(ids))
