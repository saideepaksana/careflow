from pathlib import Path

import psycopg
from psycopg.rows import dict_row

Connection = psycopg.Connection
MIGRATIONS_DIR = Path(__file__).with_name("migrations")


def connect(database_url: str) -> psycopg.Connection:
    return psycopg.connect(database_url, row_factory=dict_row)


def create_schema(conn: psycopg.Connection) -> None:
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        conn.execute(path.read_text())


def reset_schema(conn: psycopg.Connection) -> None:
    conn.execute("DROP SCHEMA public CASCADE")
    conn.execute("CREATE SCHEMA public")
    create_schema(conn)
