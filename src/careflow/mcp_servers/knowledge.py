from mcp.server.mcpserver import MCPServer

from careflow.db.connection import Connection
from careflow.knowledge.rerank import Reranker
from careflow.knowledge.search import retrieve
from careflow.mcp_servers.records import LOG_LEVEL, ok
from careflow.memory.embeddings import Embedder


def knowledge_server(
    conn: Connection, embedder: Embedder, reranker: Reranker, patient_id: str
) -> MCPServer:
    """Search over the patient's current documents and the shared guides that apply to them."""
    server = MCPServer("knowledge", log_level=LOG_LEVEL)

    @server.tool()
    def search_documents(query: str) -> dict:
        """Search the patient's current care documents and hospital guides."""
        chunks = retrieve(conn, embedder, reranker, patient_id, query)
        return ok([chunk.model_dump() for chunk in chunks])

    return server
