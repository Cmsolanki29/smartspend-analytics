#!/usr/bin/env python3
"""Generate 25k+ Indian fintech corpus rows → CSV and/or ``transaction_seed_data``."""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import execute_values

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))
load_dotenv(_BACKEND.parent / ".env")
load_dotenv(_BACKEND / ".env")

from services.indian_fintech_seed.assign import upsert_personas  # noqa: E402
from services.indian_fintech_seed.corpus_generator import corpus_validation_summary, generate_seed_corpus_rows  # noqa: E402


def _connect():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "smartspend_db"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
    )


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = list(rows[0].keys())

    def _serial(v: object) -> object:
        if v is None:
            return ""
        if hasattr(v, "quantize"):  # Decimal
            return float(v)
        return v

    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: _serial(r[k]) for k in cols})


def _insert_db(conn, rows: list[dict], clear: bool) -> None:
    cols = list(rows[0].keys())
    with conn.cursor() as cur:
        if clear:
            cur.execute("TRUNCATE transaction_seed_data RESTART IDENTITY CASCADE;")
        upsert_personas(cur)
        tuples = []
        for r in rows:
            tuples.append(tuple(r[c] for c in cols))
        col_sql = ", ".join(cols)
        sql = f"INSERT INTO transaction_seed_data ({col_sql}) VALUES %s"
        execute_values(cur, sql, tuples, page_size=1000)
    conn.commit()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--total", type=int, default=26_000, help="Row count (default 26000)")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--csv", type=str, default="", help="Write CSV to this path")
    p.add_argument("--db", action="store_true", help="Bulk insert into transaction_seed_data")
    p.add_argument("--clear-seed", action="store_true", help="TRUNCATE transaction_seed_data before insert")
    args = p.parse_args(argv)

    rows = generate_seed_corpus_rows(total=args.total, seed=args.seed)
    summary = corpus_validation_summary(rows)
    print("corpus_summary", summary)

    if args.csv:
        _write_csv(Path(args.csv), rows)
        print("wrote_csv", args.csv, "rows", len(rows))

    if args.db:
        conn = _connect()
        try:
            _insert_db(conn, rows, clear=args.clear_seed)
            print("inserted_db", len(rows), "clear_seed=", args.clear_seed)
        finally:
            conn.close()

    if not args.csv and not args.db:
        print("No --csv or --db specified; generated in memory only. Re-run with output flags.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
