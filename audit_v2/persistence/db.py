"""Minimal Postgres helpers: connect, apply schema, tenant-scoped sessions.

No migration framework — schema.py DDL is idempotent (IF NOT EXISTS /
DROP POLICY IF EXISTS) and re-applied on startup.
"""
from __future__ import annotations

import os
from contextlib import contextmanager

import psycopg

from audit_v2.persistence.schema import ALL_SCHEMA_SQL

DEFAULT_DSN_ENV = "AUDIT_PG_DSN"


def connect(dsn: str | None = None) -> psycopg.Connection:
    return psycopg.connect(dsn or os.environ[DEFAULT_DSN_ENV])


def apply_schema(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(ALL_SCHEMA_SQL)
    conn.commit()


@contextmanager
def tenant_session(conn: psycopg.Connection, tenant_id: str):
    """Transaction with app.tenant_id set; RLS policies key off this GUC.

    SET LOCAL does not accept parameterised placeholders, but tenant_id
    is an internal value (never user-supplied), so string interpolation
    is safe here.
    """
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(f"SET LOCAL app.tenant_id = '{tenant_id}'")
        yield conn
