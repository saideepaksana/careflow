import psycopg
import pytest
from langgraph.checkpoint.memory import InMemorySaver
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from careflow.db import repository
from careflow.graph.nodes import WorkflowDeps
from careflow.graph.workflow import RunContext, resume_run, start_run
from careflow.knowledge.rerank import FakeReranker
from careflow.memory.embeddings import FakeEmbedder
from tests.scripted import RoleLLM, book_lab

MESSAGE = "Please book my blood test, I live at 12 Lake Road"
ALLOWED_PREFIXES = ("careflow.", "gen_ai.", "mcp.", "jsonrpc.", "error.type")


class Crash(Exception):
    pass


def run_booking(conn: psycopg.Connection, crash_at: str | None = None) -> None:
    repository.create_conversation(conn, "conv-trace", "P001")
    deps = WorkflowDeps(conn, RoleLLM(book_lab("2026-11-03")), FakeEmbedder(), FakeReranker())
    saver = InMemorySaver()

    def crash(point: str) -> None:
        if point == crash_at:
            raise Crash(point)

    waiting = start_run(deps, saver, "conv-trace", "P001", MESSAGE, RunContext(), crash)
    resume_run(deps, saver, waiting.thread_id, "confirmation", True)


def named(spans: InMemorySpanExporter, prefix: str) -> list:
    return [s for s in spans.get_finished_spans() if s.name.startswith(prefix)]


def test_each_invocation_is_one_root_span_with_node_children(
    workflow_conn: psycopg.Connection, spans: InMemorySpanExporter
) -> None:
    run_booking(workflow_conn)
    invocations = named(spans, "careflow.invocation")
    ids = {s.context.span_id for s in invocations}
    nodes = named(spans, "workflow.node")
    assert [s.attributes["careflow.invocation"] for s in invocations] == ["start", "resume"]
    assert all(s.parent is None for s in invocations)
    assert nodes and all(s.parent.span_id in ids for s in nodes)


def test_tool_spans_sit_under_the_calling_node(
    workflow_conn: psycopg.Connection, spans: InMemorySpanExporter
) -> None:
    run_booking(workflow_conn)
    by_id = {s.context.span_id: s for s in spans.get_finished_spans()}
    [slots] = [s for s in named(spans, "execute_tool") if s.name.endswith("find_free_slots")]
    assert by_id[slots.parent.span_id].name == "workflow.node plan_schedule"
    assert slots.attributes["careflow.tool.ok"] is True


def test_audit_rows_carry_the_invocation_trace_id(
    workflow_conn: psycopg.Connection, spans: InMemorySpanExporter
) -> None:
    run_booking(workflow_conn)
    traces = [format(s.context.trace_id, "032x") for s in named(spans, "careflow.invocation")]
    rows = workflow_conn.execute(
        "SELECT trace_id, detail->'usage' AS usage FROM audit_events"
        " WHERE event = 'workflow_invocation' ORDER BY id"
    ).fetchall()
    assert [row["trace_id"] for row in rows] == traces
    assert all("elapsed_ms" in row["usage"] for row in rows)


def test_interrupt_is_not_an_error(
    workflow_conn: psycopg.Connection, spans: InMemorySpanExporter
) -> None:
    run_booking(workflow_conn)
    asks = [s for s in named(spans, "workflow.node ask_confirmation")]
    assert asks and all(s.status.status_code != StatusCode.ERROR for s in asks)


def test_spans_carry_no_patient_text(
    workflow_conn: psycopg.Connection, spans: InMemorySpanExporter
) -> None:
    run_booking(workflow_conn)
    values, keys = [], set()
    for item in spans.get_finished_spans():
        attributes = [item.attributes or {}] + [event.attributes or {} for event in item.events]
        for mapping in attributes:
            keys.update(mapping)
            values.extend(str(value) for value in mapping.values())
    assert all(key.startswith(ALLOWED_PREFIXES) for key in keys)
    assert not [v for v in values if "Lake Road" in v or "Book the blood test" in v]


def test_crash_marks_node_and_invocation_as_errors(
    workflow_conn: psycopg.Connection, spans: InMemorySpanExporter
) -> None:
    with pytest.raises(Crash):
        run_booking(workflow_conn, crash_at="before:verify")
    [verify] = named(spans, "workflow.node verify")
    [invocation] = named(spans, "careflow.invocation")
    assert verify.status.status_code == invocation.status.status_code == StatusCode.ERROR
    assert verify.attributes["error.type"] == "Crash"
