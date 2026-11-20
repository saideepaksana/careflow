from careflow.config import RECOVER_AFTER_SECONDS, load_settings
from careflow.db import repository
from careflow.db.checkpointer import open_checkpointer
from careflow.db.connection import connect
from careflow.graph.nodes import WorkflowDeps
from careflow.graph.workflow import Checkpointer, recover_run
from careflow.knowledge.rerank import FastReranker
from careflow.llm.gateway import build_llm
from careflow.memory.embeddings import FastEmbedder
from careflow.observability.tracing import setup_tracing


def recover_unless_busy(deps: WorkflowDeps, checkpointer: Checkpointer, thread_id: str) -> str:
    conversation_id = repository.get_run(deps.conn, thread_id)["conversation_id"]
    with repository.conversation_lock(deps.conn, conversation_id) as locked:
        if not locked:
            return "skipped (conversation busy)"
        return recover_run(deps, checkpointer, thread_id).status


def main() -> None:
    settings = load_settings()
    setup_tracing(settings.otel_endpoint)
    checkpointer = open_checkpointer(settings.database_url)
    with connect(settings.database_url, autocommit=True) as conn:
        deps = WorkflowDeps(conn, build_llm(settings), FastEmbedder(), FastReranker())
        threads = repository.stale_runs(conn, "running", RECOVER_AFTER_SECONDS)
        for thread_id in threads:
            print(f"{thread_id}: {recover_unless_busy(deps, checkpointer, thread_id)}")
    print(f"checked {len(threads)} runs")


if __name__ == "__main__":
    main()
