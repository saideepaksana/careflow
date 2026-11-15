import asyncio

import psycopg
import pytest
from mcp.client import Client

from careflow.agents.tools import TOOLS
from careflow.config import CORPUS_DIR
from careflow.db import repository
from careflow.knowledge.corpus import ingest_corpus
from careflow.knowledge.rerank import FakeReranker
from careflow.mcp_servers.client import McpTools
from careflow.memory.embeddings import FakeEmbedder

SERVER_TOOLS = {
    "records": {"get_care_plan", "list_appointments", "get_appointment", "find_free_slots"},
    "knowledge": {"search_documents"},
    "actions": {
        "book_appointment",
        "reschedule_appointment",
        "cancel_appointment",
        "create_coordinator_task",
        "resolve_task",
    },
}
KEYED_WRITES = SERVER_TOOLS["actions"] - {"resolve_task"}
BASELINE_TO_MCP = {"find_slots": "find_free_slots"}
TABLES = ("appointments", "coordinator_tasks", "action_results", "messages", "audit_events")


def mcp_tools(db: psycopg.Connection, patient_id: str = "P001") -> McpTools:
    return McpTools(db, patient_id, FakeEmbedder(), FakeReranker())


def schemas(tools: McpTools, server: str) -> dict[str, dict]:
    async def listing() -> object:
        async with Client(tools.servers[server]) as client:
            return await client.list_tools()

    return {tool.name: tool.input_schema for tool in asyncio.run(listing()).tools}


def table_counts(db: psycopg.Connection) -> dict[str, int]:
    return {t: db.execute(f"SELECT count(*) AS n FROM {t}").fetchone()["n"] for t in TABLES}


@pytest.mark.parametrize("server", list(SERVER_TOOLS))
def test_each_server_lists_exactly_its_tools(db: psycopg.Connection, server: str) -> None:
    listed = schemas(mcp_tools(db), server)
    assert set(listed) == SERVER_TOOLS[server]
    assert not [name for name, schema in listed.items() if "patient_id" in schema["properties"]]


def test_keyed_writes_require_idempotency_key(db: psycopg.Connection) -> None:
    listed = schemas(mcp_tools(db), "actions")
    assert all("idempotency_key" in listed[name]["required"] for name in KEYED_WRITES)


@pytest.mark.parametrize("name", [name for name in TOOLS if name != "search_documents"])
def test_baseline_arguments_match_mcp_schemas(db: psycopg.Connection, name: str) -> None:
    server = "actions" if TOOLS[name].write else "records"
    schema = schemas(mcp_tools(db), server)[BASELINE_TO_MCP.get(name, name)]
    assert set(TOOLS[name].args_model.model_fields) <= set(schema["properties"])


def test_records_tools_do_not_write(db: psycopg.Connection) -> None:
    tools, before = mcp_tools(db), table_counts(db)
    tools.read("get_care_plan")
    tools.read("list_appointments")
    tools.read("get_appointment", {"appointment_id": "A001"})
    tools.read(
        "find_free_slots",
        {"specialty": "cardiology", "start_date": "2026-11-03", "end_date": "2026-11-20"},
    )
    assert table_counts(db) == before


@pytest.mark.parametrize(("limit", "count"), [(0, 1), (1, 1), (5, 5)])
def test_slot_lists_round_trip(db: psycopg.Connection, limit: int, count: int) -> None:
    slots = mcp_tools(db).free_slots("laboratory", "2026-11-03", "2026-11-20", limit)
    assert len(slots) == count
    assert all(slot.starts_at.tzinfo is not None for slot in slots)


def test_empty_slot_list_round_trips(db: psycopg.Connection) -> None:
    assert mcp_tools(db).free_slots("laboratory", "2026-10-01", "2026-10-01", 10) == []


def test_records_are_patient_scoped(db: psycopg.Connection) -> None:
    tools = mcp_tools(db, "P002")
    assert tools.read("get_appointment", {"appointment_id": "A001"}) is None
    assert [row["id"] for row in tools.read("list_appointments")] == []


def test_extra_patient_id_argument_has_no_effect(db: psycopg.Connection) -> None:
    rows = mcp_tools(db, "P002").read("list_appointments", {"patient_id": "P001"})
    assert rows == []


def test_actions_cannot_touch_other_patients(db: psycopg.Connection) -> None:
    owner = mcp_tools(db, "P001").act(
        "create_coordinator_task",
        {"priority": "routine", "title": "t", "detail": "d", "idempotency_key": "k-owner"},
    )
    other = mcp_tools(db, "P002")
    cancel = other.act("cancel_appointment", {"appointment_id": "A001", "idempotency_key": "k-1"})
    resolve = other.act("resolve_task", {"task_id": owner["task_id"]})
    assert cancel == {"ok": False, "error": "not_found"}
    assert resolve == {"ok": False, "error": "not_found"}
    assert repository.get_task(db, owner["task_id"])["status"] == "open"


def test_task_with_foreign_thread_is_rejected(db: psycopg.Connection) -> None:
    repository.create_conversation(db, "conv-p2", "P002")
    repository.create_workflow_run(db, "conv-p2:abc", "conv-p2")
    args = {"priority": "routine", "title": "t", "detail": "d", "idempotency_key": "k-2"}
    result = mcp_tools(db, "P001").act(
        "create_coordinator_task", {**args, "kind": "approval", "thread_id": "conv-p2:abc"}
    )
    assert result == {"ok": False, "error": "invalid_thread"}


def test_same_booking_key_replays(db: psycopg.Connection) -> None:
    tools = mcp_tools(db)
    args = {
        "slot_id": "S-C08-20261103-0900",
        "care_plan_item_id": "CP001-v2-02",
        "idempotency_key": "k-3",
    }
    first, second = tools.act("book_appointment", args), tools.act("book_appointment", args)
    assert (first["replayed"], second["replayed"]) == (False, True)
    assert first["appointment_id"] == second["appointment_id"]


def test_search_returns_only_own_current_documents(db: psycopg.Connection) -> None:
    ingest_corpus(db, FakeEmbedder(), CORPUS_DIR)
    found = mcp_tools(db).search("How much fluid can I drink a day?")
    ids = [chunk["id"] for chunk in found]
    assert found and all(chunk["content"] for chunk in found)
    assert not [
        i for i in ids if i.startswith("P001-plan-v1") or i[:4] in {"P002", "P003", "P004", "P005"}
    ]
