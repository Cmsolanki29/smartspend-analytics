"""Sync PostgreSQL access (psycopg2) for SmartSpend API."""

from __future__ import annotations

from pathlib import Path
from typing import Generator

from dotenv import load_dotenv

from utils.pg_connect import connect, get_db_config

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=_PROJECT_ROOT / ".env", override=True)


def get_connection():
    cfg = get_db_config()
    if "dsn" in cfg:
        import psycopg2

        return psycopg2.connect(cfg["dsn"])
    import psycopg2

    return psycopg2.connect(
        host=cfg["host"],
        port=cfg["port"],
        dbname=cfg["dbname"],
        user=cfg["user"],
        password=cfg["password"],
    )


def get_db() -> Generator:
    """FastAPI dependency: one connection per request (commits on success)."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def test_db_connection() -> bool:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                return cur.fetchone()[0] == 1
    except Exception:
        return False
