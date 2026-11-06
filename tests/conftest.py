import json

import psycopg
import pytest

from careflow.config import load_settings
from careflow.db.connection import connect
from careflow.db.seed import seed

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


@pytest.fixture(scope="module")
def seeded_db_url() -> str:
    url = load_settings().test_database_url
    try:
        connect(url).close()
    except psycopg.OperationalError:
        pytest.skip("test database is not reachable")
    seed(url)
    return url


@pytest.fixture
def db(seeded_db_url: str):
    with connect(seeded_db_url) as conn:
        yield conn
        conn.rollback()
