from careflow.config import load_settings
from careflow.db import repository
from careflow.db.checkpointer import open_checkpointer
from careflow.db.connection import connect
from careflow.graph.nodes import WorkflowDeps
from careflow.graph.workflow import recover_run
from careflow.knowledge.rerank import FastReranker
from careflow.llm.gateway import build_llm
from careflow.memory.embeddings import FastEmbedder


def main() -> None:
    settings = load_settings()
    checkpointer = open_checkpointer(settings.database_url)
    with connect(settings.database_url, autocommit=True) as conn:
        deps = WorkflowDeps(conn, build_llm(settings), FastEmbedder(), FastReranker())
        threads = repository.runs_with_status(conn, "running")
        for thread_id in threads:
            result = recover_run(deps, checkpointer, thread_id)
            print(f"{thread_id}: {result.status}")
    print(f"recovered {len(threads)} runs")


if __name__ == "__main__":
    main()
