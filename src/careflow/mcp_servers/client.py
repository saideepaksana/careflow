import asyncio
import json
from datetime import date, datetime

from mcp.client import Client
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel

from careflow.db.connection import Connection
from careflow.knowledge.rerank import Reranker
from careflow.mcp_servers.actions import actions_server
from careflow.mcp_servers.knowledge import knowledge_server
from careflow.mcp_servers.records import records_server
from careflow.memory.embeddings import Embedder


class McpToolError(Exception):
    """A tool call failed inside the server (a bug or a database outage); the server logs why."""


class Slot(BaseModel):
    id: str
    starts_at: datetime
    clinician_name: str


class PlanItem(BaseModel):
    id: str
    kind: str
    description: str
    specialty: str | None = None
    due_date: date | None = None


class CarePlanView(BaseModel):
    id: str
    published_on: date
    items: list[PlanItem]


async def call_tool(server: MCPServer, tool: str, args: dict) -> object:
    async with Client(server) as client:
        return await client.call_tool(tool, args)


class McpTools:
    """Synchronous access to the records, knowledge and actions servers for one patient."""

    def __init__(
        self, conn: Connection, patient_id: str, embedder: Embedder, reranker: Reranker
    ) -> None:
        self.servers = {
            "records": records_server(conn, patient_id),
            "knowledge": knowledge_server(conn, embedder, reranker, patient_id),
            "actions": actions_server(conn, patient_id),
        }

    def call(self, server: str, tool: str, args: dict) -> dict:
        plain = json.loads(json.dumps(args, default=str))
        result = asyncio.run(call_tool(self.servers[server], tool, plain))
        if result.is_error or len(result.content) != 1:
            raise McpToolError(tool)
        return json.loads(result.content[0].text)

    def read_envelope(self, tool: str, args: dict | None = None) -> dict:
        return self.call("records", tool, args or {})

    def read(self, tool: str, args: dict | None = None) -> object:
        envelope = self.read_envelope(tool, args)
        return envelope["data"] if envelope["ok"] else None

    def search(self, query: str) -> list[dict]:
        envelope = self.call("knowledge", "search_documents", {"query": query})
        return envelope["data"] if envelope["ok"] else []

    def act(self, tool: str, args: dict) -> dict:
        return self.call("actions", tool, args)

    def care_plan(self) -> CarePlanView | None:
        data = self.read("get_care_plan")
        return CarePlanView.model_validate(data) if data else None

    def free_slots(self, specialty: str, start: date, end: date, limit: int) -> list[Slot]:
        args = {"specialty": specialty, "start_date": start, "end_date": end, "limit": limit}
        return [Slot.model_validate(row) for row in self.read("find_free_slots", args) or []]
