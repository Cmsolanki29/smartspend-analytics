#!/usr/bin/env python3
"""Reproduce upload RecursionError locally."""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from services.document_parser_service import classify_and_extract_monster, extract_text_from_bytes
from services.transaction_upsert import enrich_transaction_row
from services.monster_extraction import extract_with_retry
from services.pdf_parser import PDFParserAgent
from services.statement_line_parser import parse_axis_style_statement

PDF = _BACKEND.parent / "test samples" / "onboarding" / "AXIS_SUMIT_ONBOARDING_STATEMENT_Sumit_Dabas.pdf"


def main() -> None:
    content = PDF.read_bytes()
    print("=== enrich_transaction_row (recursion probe) ===")
    try:
        enrich_transaction_row(
            {"merchant": "Swiggy", "description": "UPI Swiggy", "category": "food"}
        )
        print("enrich ok")
    except RecursionError:
        traceback.print_exc()

    print("=== extract_text ===")
    text = extract_text_from_bytes(content, PDF.name)
    print("text len", len(text))

    print("=== axis line parser ===")
    det = parse_axis_style_statement(text)
    print("deterministic", len(det))

    print("=== classify_and_extract_monster ===")
    try:
        parsed = classify_and_extract_monster(text=text, filename=PDF.name)
        print("txns", len(parsed.get("transactions") or []), "method", parsed.get("method"))
    except RecursionError:
        traceback.print_exc()

    print("=== monster extract_with_retry (no db) ===")
    try:
        ex = extract_with_retry(content, PDF.name, 1, 1, None)
        print("quality", ex.get("quality_score"), "text", len(ex.get("text") or ""))
    except RecursionError:
        traceback.print_exc()


if __name__ == "__main__":
    main()
