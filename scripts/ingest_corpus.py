from careflow.config import CORPUS_DIR, load_settings
from careflow.db.connection import connect
from careflow.knowledge.corpus import ingest_corpus
from careflow.memory.embeddings import FastEmbedder


def main() -> None:
    with connect(load_settings().database_url) as conn:
        count = ingest_corpus(conn, FastEmbedder(), CORPUS_DIR)
    print(f"ingested {count} chunks from {CORPUS_DIR.name}/")


if __name__ == "__main__":
    main()
