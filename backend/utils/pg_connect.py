"""Shared psycopg2 connection — Neon ``DATABASE_URL`` or legacy ``DB_*`` vars."""

from __future__ import annotations

import os

import psycopg2
from psycopg2.extensions import connection as PgConnection


def normalize_database_url(url: str) -> str:
    u = (url or "").strip()
    if u.startswith("postgres://"):
        return "postgresql://" + u[len("postgres://") :]
    return u


def connect() -> PgConnection:
    url = os.getenv("DATABASE_URL", "").strip()
    if url:
        return psycopg2.connect(normalize_database_url(url))
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME", "smartspend_db"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
    )


def get_db_config() -> dict[str, str | int]:
    """Individual fields for callers that need a dict (not a DSN)."""
    url = os.getenv("DATABASE_URL", "").strip()
    if url:
        return {"dsn": normalize_database_url(url)}
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "dbname": os.getenv("DB_NAME", "smartspend_db"),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD", ""),
    }
