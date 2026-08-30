"""PostgreSQL persistence using the same parameterized analytical queries."""

from contextlib import contextmanager
from pathlib import Path
import re

import psycopg
from psycopg.rows import dict_row

from chesslab.storage import SQLiteGameStorage


def postgres_query(query: str) -> str:
    """Translate our qmark binds, preserving quoted literals (never interpolate values)."""
    query = query.replace("INSTR(game.opening, ':')", "STRPOS(game.opening, ':')")
    query = query.replace("%", "%%")
    return re.sub(r"'(?:''|[^'])*'|\?", lambda match: "%s" if match.group() == "?" else match.group(), query)


class PostgresConnection:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, query, parameters=()):
        return self.connection.execute(postgres_query(query), parameters)


class PostgresGameStorage(SQLiteGameStorage):
    """Shared storage operations, with PostgreSQL connections and explicit migrations."""

    def __init__(self, database_url: str):
        self.database_url = database_url

    @contextmanager
    def _connect(self):
        with psycopg.connect(self.database_url, row_factory=dict_row, connect_timeout=10) as connection:
            connection.execute("SET LOCAL statement_timeout = '30s'")
            yield PostgresConnection(connection)

    def migrate(self):
        with self._connect() as connection:
            connection.execute("SELECT pg_advisory_xact_lock(724501)")
            connection.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY)")
            for migration in sorted((Path(__file__).resolve().parents[1] / "migrations").glob("*.sql")):
                if connection.execute("SELECT name FROM schema_migrations WHERE name = ?", (migration.name,)).fetchone():
                    continue
                for statement in migration.read_text(encoding="utf-8").split(';'):
                    if statement.strip():
                        connection.execute(statement)
                connection.execute("INSERT INTO schema_migrations(name) VALUES (?)", (migration.name,))
