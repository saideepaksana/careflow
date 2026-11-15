import json

import psycopg
import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from careflow.config import CORPUS_DIR, load_settings
from careflow.db.connection import connect
from careflow.db.seed import seed
from careflow.knowledge.corpus import ingest_corpus
from careflow.memory.embeddings import FakeEmbedder
from careflow.observability.tracing import setup_tracing

RUNNING_EXAMPLE = {
    "items": [
        {
            "kind": "appointment_request",
            "summary": "Reschedule cardiology visit to next Wednesday",
            "appointment_action": "reschedule",
            "specialty": "cardiology",
            "preferred_time": "next Wednesday",
        },
        {
            "kind": "symptom_report",
            "summary": "Ankle swelling and 2.5 kg weight gain",
            "symptoms": ["ankle swelling", "weight gain"],
            "measurements": [{"name": "weight_change_kg", "value": 2.5}],
        },
    ],
    "urgency": "urgent",
}


@pytest.fixture
def running_example_reply() -> str:
    return json.dumps(RUNNING_EXAMPLE)


def reachable_test_db_url() -> str:
    url = load_settings().test_database_url
    try:
        connect(url).close()
    except psycopg.OperationalError:
        pytest.skip("test database is not reachable")
    return url


@pytest.fixture(scope="module")
def seeded_db_url() -> str:
    url = reachable_test_db_url()
    seed(url)
    return url


@pytest.fixture
def fresh_db_url() -> str:
    url = reachable_test_db_url()
    seed(url)
    with connect(url, autocommit=True) as conn:
        ingest_corpus(conn, FakeEmbedder(), CORPUS_DIR)
    return url


@pytest.fixture
def workflow_conn(fresh_db_url: str):
    with connect(fresh_db_url, autocommit=True) as conn:
        yield conn


@pytest.fixture
def db(seeded_db_url: str):
    with connect(seeded_db_url) as conn:
        yield conn
        conn.rollback()


@pytest.fixture(scope="session")
def span_exporter() -> InMemorySpanExporter:
    exporter = InMemorySpanExporter()
    setup_tracing(exporter=exporter)
    return exporter


@pytest.fixture
def spans(span_exporter: InMemorySpanExporter) -> InMemorySpanExporter:
    span_exporter.clear()
    return span_exporter
