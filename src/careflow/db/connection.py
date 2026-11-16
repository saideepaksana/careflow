from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

Connection = psycopg.Connection
MIGRATIONS_DIR = Path(__file__).with_name("migrations")


def connect(database_url: str, autocommit: bool = False) -> psycopg.Connection:
    return psycopg.connect(database_url, row_factory=dict_row, autocommit=autocommit)


def create_schema(conn: psycopg.Connection) -> None:
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        conn.execute(path.read_text())


def reset_schema(conn: psycopg.Connection) -> None:
    conn.execute("DROP SCHEMA public CASCADE")
    conn.execute("CREATE SCHEMA public")
    create_schema(conn)


def database_url_for(database_url: str, name: str) -> str:
    base, _, _ = database_url.rpartition("/")
    return f"{base}/{name}"


def clone_database(database_url: str, template: str, target: str) -> str:
    """Recreate `target` as a copy of `template`; returns the target's URL."""
    with connect(database_url_for(database_url, "postgres"), autocommit=True) as admin:
        admin.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(target))
        )
        admin.execute(
            sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                sql.Identifier(target), sql.Identifier(template)
            )
        )
    return database_url_for(database_url, target)


def recreate_database(database_url: str, name: str) -> str:
    """Drop and create an empty database; returns its URL."""
    with connect(database_url_for(database_url, "postgres"), autocommit=True) as admin:
        admin.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
        )
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    return database_url_for(database_url, name)
