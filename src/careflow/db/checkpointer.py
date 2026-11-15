import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row


def checkpointer_connection(database_url: str) -> psycopg.Connection:
    return psycopg.connect(database_url, autocommit=True, prepare_threshold=0, row_factory=dict_row)


def open_checkpointer(database_url: str) -> PostgresSaver:
    return PostgresSaver(checkpointer_connection(database_url))


def setup_checkpointer(database_url: str) -> None:
    with checkpointer_connection(database_url) as conn:
        PostgresSaver(conn).setup()
