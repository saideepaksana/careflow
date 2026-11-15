import os
import sys

from careflow.config import load_settings
from careflow.db import repository
from careflow.db.connection import connect
from careflow.knowledge.rerank import FastReranker
from careflow.mcp_servers.client import McpTools
from careflow.memory.embeddings import FastEmbedder

READ_ONLY_SERVERS = ("records", "knowledge")
USAGE = "usage: CAREFLOW_PATIENT_ID=P001 python scripts/serve_mcp.py {records|knowledge}"


def main() -> None:
    name = sys.argv[1] if len(sys.argv) == 2 else ""
    patient_id = os.environ.get("CAREFLOW_PATIENT_ID", "")
    if name not in READ_ONLY_SERVERS:
        sys.exit(USAGE)
    conn = connect(load_settings().database_url, autocommit=True)
    if repository.get_patient(conn, patient_id) is None:
        sys.exit(f"unknown patient {patient_id!r}\n{USAGE}")
    tools = McpTools(conn, patient_id, FastEmbedder(), FastReranker())
    tools.servers[name].run("stdio")


if __name__ == "__main__":
    main()
