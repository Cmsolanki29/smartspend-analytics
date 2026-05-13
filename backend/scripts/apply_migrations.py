"""Apply every ``*.sql`` file in ``backend/database/migrations/`` in
filename order.

Idempotent: keeps a ``_migration_history`` table that records each
applied filename + checksum.  Already-applied files are skipped.

Usage::

    cd backend
    python -m scripts.apply_migrations              # apply everything
    python -m scripts.apply_migrations --dry-run    # show plan, no-op

This script intentionally uses ``psycopg2`` (synchronous) because
migrations should never be the hot path and a clean blocking
implementation is trivial to reason about.

audit-7: documents and codifies the canonical migration directory.
See ``backend/database/migrations/README.md``.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import sys
from pathlib import Path
from typing import Iterable

import psycopg2
from dotenv import load_dotenv
from psycopg2.extensions import connection as PgConnection

logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parent.parent
# Project root .env (same pattern as backend/db.py) then optional backend/.env
load_dotenv(_BACKEND_DIR.parent / ".env")
load_dotenv(_BACKEND_DIR / ".env")


_MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "database" / "migrations"
_HISTORY_DDL = """
CREATE TABLE IF NOT EXISTS _migration_history (
    id              SERIAL PRIMARY KEY,
    filename        TEXT NOT NULL UNIQUE,
    checksum_sha256 TEXT NOT NULL,
    applied_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def _connect() -> PgConnection:
    """Open a synchronous connection from the standard env vars."""
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "smartspend_db"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
    )


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _list_migrations() -> list[Path]:
    return sorted(p for p in _MIGRATIONS_DIR.glob("*.sql"))


def _ensure_history_table(conn: PgConnection) -> None:
    with conn.cursor() as cur:
        cur.execute(_HISTORY_DDL)
    conn.commit()


def _already_applied(conn: PgConnection) -> set[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT filename FROM _migration_history")
        return {row[0] for row in cur.fetchall()}


def _apply_one(conn: PgConnection, path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    cs = _checksum(path)
    with conn.cursor() as cur:
        cur.execute(sql)
        cur.execute(
            "INSERT INTO _migration_history(filename, checksum_sha256) "
            "VALUES (%s, %s)",
            (path.name, cs),
        )
    conn.commit()


def _plan(applied: set[str], all_files: Iterable[Path]) -> list[Path]:
    return [p for p in all_files if p.name not in applied]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print which files would be applied without running them.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    files = _list_migrations()
    if not files:
        print(f"No .sql files in {_MIGRATIONS_DIR}")
        return 0

    conn = _connect()
    try:
        _ensure_history_table(conn)
        applied = _already_applied(conn)
        pending = _plan(applied, files)

        print(f"Migrations dir: {_MIGRATIONS_DIR}")
        print(f"Total files:    {len(files)}")
        print(f"Already applied {len(applied)}, pending {len(pending)}")
        for p in pending:
            print(f"  pending: {p.name}")

        if args.dry_run:
            return 0

        for p in pending:
            print(f"applying {p.name} ...", end=" ", flush=True)
            try:
                _apply_one(conn, p)
                print("ok")
            except Exception as exc:  # noqa: BLE001
                conn.rollback()
                print(f"FAILED: {exc}")
                logger.error("migration %s failed: %s", p.name, exc)
                return 2
        print(f"applied {len(pending)} new migrations")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
