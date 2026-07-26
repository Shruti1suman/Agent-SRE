from contextlib import closing
from datetime import date, datetime
from decimal import Decimal
import json
import re
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from backend.core.settings import settings


DATABASE_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


def normalize(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, list):
        return [normalize(item) for item in value]
    if isinstance(value, dict):
        return {key: normalize(item) for key, item in value.items()}
    return value


def json_value(value: Any) -> Any:
    if isinstance(value, dict | list):
        return value
    if value in (None, ""):
        return None
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return value


class PostgresStore:
    def __init__(self, database: str):
        if not DATABASE_NAME_PATTERN.fullmatch(database):
            raise ValueError(f"Invalid PostgreSQL database name: {database!r}")
        self.database = database

    def fetch_all(self, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        try:
            with closing(self._connect()) as connection:
                with connection.cursor(row_factory=dict_row) as cursor:
                    cursor.execute(query, params)
                    return [normalize(dict(row)) for row in cursor.fetchall()]
        except Exception as exc:
            return [{"error": str(exc)}]

    def fetch_one(self, query: str, params: tuple[Any, ...] = ()) -> dict[str, Any]:
        rows = self.fetch_all(query, params)
        return rows[0] if rows else {}

    def execute(self, query: str, params: tuple[Any, ...] = ()) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)

    def execute_script(self, statements: list[str]) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                for statement in statements:
                    cursor.execute(statement)

    def ensure_database(self) -> None:
        with psycopg.connect(
            host=settings.postgres_host,
            port=settings.postgres_port,
            user=settings.postgres_user,
            password=settings.postgres_password,
            dbname=settings.postgres_maintenance_database,
            autocommit=True,
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (self.database,))
                if cursor.fetchone() is None:
                    cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(self.database)))

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(
            host=settings.postgres_host,
            port=settings.postgres_port,
            user=settings.postgres_user,
            password=settings.postgres_password,
            dbname=self.database,
        )
