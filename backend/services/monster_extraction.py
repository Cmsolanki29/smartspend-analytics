"""
Monster-level document text extraction with quality gate and retry cascade.

Stage 1–2.5 of the upload pipeline: file intelligence, full text extraction, quality scoring.
"""
from __future__ import annotations

import io
import json
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

_QUALITY_PASS_THRESHOLD = 70
_MAX_STORED_TEXT = 500_000

_TESSERACT_WINDOWS_CANDIDATES = (
    Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
)


def _configure_tesseract() -> bool:
    """Point pytesseract at the system Tesseract binary (Windows-friendly)."""
    try:
        import pytesseract
    except ImportError:
        return False

    env_cmd = (os.getenv("TESSERACT_CMD") or "").strip()
    if env_cmd and Path(env_cmd).is_file():
        pytesseract.pytesseract.tesseract_cmd = env_cmd
        return True

    if shutil.which("tesseract"):
        return True

    for candidate in _TESSERACT_WINDOWS_CANDIDATES:
        if candidate.is_file():
            pytesseract.pytesseract.tesseract_cmd = str(candidate)
            logger.info("Using Tesseract at %s", candidate)
            return True

    return False


def get_extension(filename: str) -> str:
    return (filename or "").rsplit(".", 1)[-1].lower() if "." in (filename or "") else ""


def extract_text_monster(content: bytes, filename: str) -> dict[str, Any]:
    """Extract full text from any supported file type (no truncation)."""
    ext = get_extension(filename)

    if ext == "pdf":
        return _extract_pdf_monster(content)
    if ext == "csv":
        return _extract_csv_monster(content)
    if ext in ("xlsx", "xls"):
        return _extract_excel_monster(content, ext)
    if ext in ("txt", "text"):
        return _extract_text_file(content)
    if ext in ("jpg", "jpeg", "png", "tiff", "bmp", "webp"):
        return _extract_image_monster(content)
    return {
        "text": "",
        "method": "unsupported",
        "quality_score": 0,
        "file_type": ext,
        "pages": [],
        "tables": [],
        "error": f"Unsupported: .{ext}",
    }


def _calculate_quality_score(result: dict[str, Any]) -> int:
    text = (result.get("text") or "").strip()
    pages = result.get("pages") or []
    if not text and not pages:
        return 0
    score = 0
    if len(text) > 500:
        score += 40
    elif len(text) > 100:
        score += 25
    elif len(text) > 20:
        score += 10
    dates = len(re.findall(r"\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4}", text))
    amounts = len(re.findall(r"[\d,]+\.\d{2}|₹[\d,]+", text))
    if dates > 0:
        score += min(30, dates * 3)
    if amounts > 0:
        score += min(30, amounts * 2)
    if pages and all(len((p.get("text") or "").strip()) > 30 for p in pages):
        score += 10
    return min(100, score)


def _extract_pdf_monster(content: bytes) -> dict[str, Any]:
    """pdfplumber (+ optional fitz). OCR per-page only when not in fast-upload mode."""
    fast = _fast_upload_enabled()
    results: dict[str, Any] = {
        "file_type": "pdf",
        "pages": [],
        "tables": [],
        "text": "",
        "method": "",
        "quality_score": 0,
    }
    all_text_parts: list[str] = []
    all_tables: list[Any] = []
    methods_used: list[str] = []

    try:
        import pdfplumber

        with pdfplumber.open(io.BytesIO(content)) as pdf:
            results["page_count"] = len(pdf.pages)
            for i, page in enumerate(pdf.pages):
                page_text = ""
                page_tables: list[Any] = []
                page_method = "none"

                try:
                    tables = page.extract_tables()
                    if tables:
                        for table in tables:
                            for row in table:
                                if row:
                                    cleaned = [str(cell).strip() if cell else "" for cell in row]
                                    page_text += " | ".join(cleaned) + "\n"
                            page_tables.extend(tables)
                        page_method = "pdfplumber_tables"
                except Exception as exc:
                    logger.warning("Table extraction failed page %s: %s", i, exc)

                try:
                    text_result = page.extract_text() or ""
                    if len(text_result.strip()) > len(page_text.strip()):
                        page_text = text_result
                        page_method = "pdfplumber_text"
                except Exception as exc:
                    logger.warning("Text extraction failed page %s: %s", i, exc)

                # Fast upload: skip Tesseract (5–15s/page) when pdfplumber already has table/text.
                if not fast and len(page_text.strip()) < 50:
                    ocr_text = _ocr_pdf_page(content, i)
                    if len(ocr_text.strip()) > len(page_text.strip()):
                        page_text = ocr_text
                        page_method = "ocr_tesseract"

                results["pages"].append({
                    "page": i + 1,
                    "text": page_text,
                    "method": page_method,
                    "char_count": len(page_text),
                })
                all_text_parts.append(page_text)
                all_tables.extend(page_tables)
                methods_used.append(page_method)
    except Exception as exc:
        logger.error("pdfplumber failed: %s", exc)

    plumber_text = "\n".join(all_text_parts)

    # Fast upload: one engine only — avoid re-opening PDF with fitz (saves ~1–2s).
    if fast and len(plumber_text.strip()) > 100:
        results["text"] = plumber_text
        results["method"] = (
            "pdfplumber_tables" if "pdfplumber_tables" in methods_used else "pdfplumber_text"
        )
    else:
        try:
            import fitz

            doc = fitz.open(stream=content, filetype="pdf")
            fitz_parts = [page.get_text("text") or "" for page in doc]
            doc.close()
            fitz_text = "\n".join(fitz_parts)

            if len(fitz_text.strip()) > len(plumber_text.strip()) * 1.2:
                results["text"] = fitz_text
                results["method"] = "fitz"
                if not results["pages"]:
                    results["pages"] = [
                        {"page": i + 1, "text": t, "method": "fitz", "char_count": len(t)}
                        for i, t in enumerate(fitz_parts)
                    ]
            else:
                results["text"] = plumber_text
                results["method"] = (
                    "pdfplumber_tables" if "pdfplumber_tables" in methods_used else "pdfplumber_text"
                )
        except ImportError:
            results["text"] = plumber_text
            results["method"] = methods_used[0] if methods_used else "pdfplumber"
        except Exception as exc:
            logger.warning("PyMuPDF failed: %s", exc)
            results["text"] = plumber_text
            results["method"] = methods_used[0] if methods_used else "pdfplumber"

    results["tables"] = all_tables
    if not results.get("page_count"):
        results["page_count"] = len(results["pages"]) or 1
    results["quality_score"] = _calculate_quality_score(results)
    return results


def _ocr_pdf_page(content: bytes, page_num: int) -> str:
    try:
        import fitz
        import pytesseract
        from PIL import Image, ImageEnhance, ImageFilter

        if not _configure_tesseract():
            logger.warning("Tesseract binary not found — set TESSERACT_CMD in .env")
            return ""

        doc = fitz.open(stream=content, filetype="pdf")
        page = doc[page_num]
        mat = fitz.Matrix(300 / 72, 300 / 72)
        pix = page.get_pixmap(matrix=mat)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        doc.close()

        img = img.convert("L")
        img = ImageEnhance.Contrast(img).enhance(2.0)
        img = img.filter(ImageFilter.SHARPEN)
        img = img.point(lambda x: 0 if x < 140 else 255)

        text = pytesseract.image_to_string(img, config="--oem 3 --psm 6")
        return _post_ocr_cleanup(text)
    except ImportError:
        logger.warning("OCR dependencies not installed")
        return ""
    except Exception as exc:
        logger.warning("OCR failed page %s: %s", page_num, exc)
        return ""


def _post_ocr_cleanup(text: str) -> str:
    text = re.sub(r"(\d),B(\d)", r"\1,8\2", text)
    text = re.sub(r"(\d),O(\d)", r"\1,0\2", text)
    text = re.sub(r"\bl(\d)", r"1\1", text)
    text = re.sub(r"\.OO\b", ".00", text)
    text = re.sub(r"\.O(\d)", r".0\1", text)
    return text


def _extract_csv_monster(content: bytes) -> dict[str, Any]:
    encoding = "utf-8"
    delimiter = ","

    try:
        import chardet

        detected = chardet.detect(content[:10000])
        encoding = detected.get("encoding") or "utf-8"
    except ImportError:
        pass

    try:
        text = content.decode(encoding, errors="replace")
    except Exception:
        text = content.decode("utf-8", errors="replace")

    try:
        import csv

        sniffer = csv.Sniffer()
        delimiter = sniffer.sniff(text[:5000]).delimiter
    except Exception:
        delimiter = ","

    result: dict[str, Any] = {
        "file_type": "csv",
        "text": text,
        "method": "csv_raw",
        "pages": [{"page": 1, "text": text, "method": "csv_raw", "char_count": len(text)}],
        "tables": [],
        "encoding": encoding,
        "delimiter": delimiter,
    }

    try:
        import pandas as pd
        from services.bank_parser import BankStatementParser

        df = pd.read_csv(
            io.BytesIO(content), encoding=encoding, sep=delimiter, on_bad_lines="skip"
        )
        parser = BankStatementParser()
        bank_txns = parser.parse_dataframe(df)
        if bank_txns:
            result["method"] = "bank_parser_deterministic"
            result["tables"] = [bank_txns]
            result["quality_score"] = 95
            return result
    except Exception as exc:
        logger.info("bank_parser didn't match: %s", exc)

    try:
        import pandas as pd

        df = pd.read_csv(
            io.BytesIO(content), encoding=encoding, sep=delimiter, on_bad_lines="skip"
        )
        col_text = " ".join(str(c).lower() for c in df.columns)
        date_cols = [
            c for c in df.columns
            if any(k in str(c).lower() for k in ("date", "txn", "transaction", "value", "posting"))
        ]
        amount_cols = [
            c for c in df.columns
            if any(
                k in str(c).lower()
                for k in ("amount", "debit", "credit", "withdrawal", "deposit", "dr", "cr")
            )
        ]
        desc_cols = [
            c for c in df.columns
            if any(
                k in str(c).lower()
                for k in ("narration", "description", "particular", "remark", "detail", "merchant", "payee")
            )
        ]
        if date_cols and amount_cols:
            cols = list(dict.fromkeys([*date_cols, *desc_cols, *amount_cols]))
            matched_df = df[cols].copy()
            result["method"] = "csv_fuzzy_columns"
            result["text"] = f"Columns: {list(matched_df.columns)}\n\n{matched_df.to_string(index=False)}"
            result["tables"] = [matched_df.to_dict("records")]
            result["quality_score"] = 80
            return result
    except Exception as exc:
        logger.info("Fuzzy column matching failed: %s", exc)

    result["quality_score"] = _calculate_quality_score(result)
    return result


def _extract_excel_monster(content: bytes, ext: str) -> dict[str, Any]:
    try:
        import pandas as pd

        engine = "openpyxl" if ext == "xlsx" else "xlrd"
        xls = pd.ExcelFile(io.BytesIO(content), engine=engine)
        best_sheet = None
        best_df = None
        best_score = 0
        all_text: list[str] = []

        for sheet_name in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=sheet_name)
            score = 0
            col_text = " ".join(str(c).lower() for c in df.columns)
            if any(k in col_text for k in ("date", "txn", "transaction")):
                score += 30
            if any(k in col_text for k in ("amount", "debit", "credit")):
                score += 30
            if any(k in col_text for k in ("narration", "description", "merchant")):
                score += 20
            if len(df) > 5:
                score += 20
            all_text.append(f"--- Sheet: {sheet_name} ---")
            all_text.append(f"Columns: {list(df.columns)}")
            all_text.append(df.to_string(index=False))
            if score > best_score:
                best_score = score
                best_sheet = sheet_name
                best_df = df

        full_text = "\n".join(all_text)
        result: dict[str, Any] = {
            "file_type": "excel",
            "text": full_text,
            "method": "pandas_excel",
            "pages": [{"page": 1, "text": full_text, "method": "pandas_excel", "char_count": len(full_text)}],
            "tables": [best_df.to_dict("records")] if best_df is not None else [],
            "best_sheet": best_sheet,
            "sheet_names": xls.sheet_names,
            "quality_score": 85 if best_score > 50 else 50,
        }

        if best_df is not None:
            try:
                from services.bank_parser import BankStatementParser

                bank_txns = BankStatementParser().parse_dataframe(best_df)
                if bank_txns:
                    result["method"] = "excel_bank_parser"
                    result["tables"] = [bank_txns]
                    result["quality_score"] = 95
            except Exception:
                pass
        return result
    except ImportError as exc:
        return {
            "text": "",
            "method": "excel_failed",
            "quality_score": 0,
            "file_type": "excel",
            "pages": [],
            "tables": [],
            "error": f"Missing library: {exc}. pip install openpyxl xlrd",
        }
    except Exception as exc:
        return {
            "text": "",
            "method": "excel_failed",
            "quality_score": 0,
            "file_type": "excel",
            "pages": [],
            "tables": [],
            "error": f"Excel parse error: {exc}",
        }


def _extract_image_monster(content: bytes) -> dict[str, Any]:
    try:
        import pytesseract
        from PIL import Image, ImageEnhance, ImageFilter

        if not _configure_tesseract():
            return {
                "text": "",
                "method": "ocr_unavailable",
                "quality_score": 0,
                "file_type": "image",
                "pages": [],
                "tables": [],
                "error": (
                    "Tesseract not found. Install from https://github.com/UB-Mannheim/tesseract/wiki "
                    "or set TESSERACT_CMD in .env to tesseract.exe path."
                ),
            }

        img = Image.open(io.BytesIO(content))
        img_processed = img.convert("L")
        img_processed = ImageEnhance.Contrast(img_processed).enhance(2.0)
        img_processed = img_processed.filter(ImageFilter.SHARPEN)
        img_processed = img_processed.point(lambda x: 0 if x < 140 else 255)
        text = pytesseract.image_to_string(img_processed, config="--oem 3 --psm 6")
        text = _post_ocr_cleanup(text)
        payload = {"text": text, "pages": [{"text": text}], "file_type": "image"}
        return {
            "file_type": "image",
            "text": text,
            "method": "ocr_tesseract",
            "pages": [{"page": 1, "text": text, "method": "ocr_tesseract", "char_count": len(text)}],
            "tables": [],
            "quality_score": _calculate_quality_score(payload),
        }
    except ImportError:
        return {
            "text": "",
            "method": "ocr_unavailable",
            "quality_score": 0,
            "file_type": "image",
            "pages": [],
            "tables": [],
            "error": "pip install pytesseract Pillow; install tesseract-ocr system package",
        }
    except Exception as exc:
        return {
            "text": "",
            "method": "ocr_failed",
            "quality_score": 0,
            "file_type": "image",
            "pages": [],
            "tables": [],
            "error": str(exc),
        }


def _extract_text_file(content: bytes) -> dict[str, Any]:
    for enc in ("utf-8", "latin-1", "cp1252", "iso-8859-1"):
        try:
            text = content.decode(enc)
            payload = {"text": text, "pages": [{"text": text}], "file_type": "txt"}
            return {
                "file_type": "txt",
                "text": text,
                "method": "text_decode",
                "pages": [{"page": 1, "text": text, "method": "text_decode", "char_count": len(text)}],
                "tables": [],
                "quality_score": _calculate_quality_score(payload),
            }
        except Exception:
            continue
    return {"text": "", "method": "decode_failed", "quality_score": 0, "file_type": "txt", "pages": [], "tables": []}


# ── Quality gate ──────────────────────────────────────────────────────────────


def quality_gate(extraction_result: dict[str, Any], original_content: bytes | None = None) -> dict[str, Any]:
    text = extraction_result.get("text", "") or ""
    pages = extraction_result.get("pages", []) or []
    file_type = extraction_result.get("file_type", "")
    checks: dict[str, Any] = {}
    issues: list[str] = []
    total_score = 0

    if file_type == "pdf" and extraction_result.get("page_count"):
        expected_pages = extraction_result["page_count"]
        pages_with_text = sum(1 for p in pages if len((p.get("text") or "").strip()) > 50)
        page_score = min(30, int(30 * pages_with_text / max(expected_pages, 1)))
        checks["page_count"] = {
            "score": page_score,
            "max": 30,
            "detail": f"{pages_with_text}/{expected_pages} pages have text",
        }
        if pages_with_text < expected_pages:
            issues.append(f"Only {pages_with_text} of {expected_pages} pages have extractable text")
    else:
        page_score = 30 if len(text.strip()) > 100 else (15 if len(text.strip()) > 20 else 0)
        checks["page_count"] = {"score": page_score, "max": 30, "detail": f"Text length: {len(text)} chars"}
    total_score += page_score

    if pages:
        char_counts = [len((p.get("text") or "").strip()) for p in pages]
        avg_chars = sum(char_counts) / len(char_counts) if char_counts else 0
        density_score = min(20, int(20 * min(avg_chars, 500) / 500))
        checks["text_density"] = {
            "score": density_score,
            "max": 20,
            "detail": f"Average {int(avg_chars)} chars/page",
        }
        if avg_chars < 100:
            issues.append(f"Low text density: avg {int(avg_chars)} chars/page")
    else:
        density_score = 20 if len(text) > 200 else (10 if len(text) > 50 else 0)
        checks["text_density"] = {"score": density_score, "max": 20, "detail": f"{len(text)} chars total"}
    total_score += density_score

    date_patterns = re.findall(
        r"\b\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4}\b"
        r"|\b\d{1,2}[-\s](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[-\s]\d{2,4}\b",
        text,
        re.IGNORECASE,
    )
    amount_patterns = re.findall(
        r"[\d,]+\.\d{2}|₹[\d,]+|\bINR\s*[\d,]+|\b\d{2,},\d{3}",
        text,
    )
    found_dates = len(date_patterns)
    found_amounts = len(amount_patterns)
    if found_dates > 0 and found_amounts > 0:
        marker_score = min(25, int(25 * min(found_dates, 10) / 10))
    elif found_dates > 0 or found_amounts > 0:
        marker_score = 10
    else:
        marker_score = 0
        issues.append("No financial markers (dates/amounts) found in extracted text")
    checks["financial_markers"] = {
        "score": marker_score,
        "max": 25,
        "detail": f"Found {found_dates} dates, {found_amounts} amounts",
    }
    total_score += marker_score

    anchors_found: list[str] = []
    anchor_keywords = [
        "statement", "account", "balance", "opening", "closing",
        "hdfc", "axis", "sbi", "icici", "kotak", "bob", "pnb", "canara", "union",
        "credit card", "debit", "credit", "transaction", "period", "from", "to",
    ]
    text_lower = text.lower()
    for keyword in anchor_keywords:
        if keyword in text_lower:
            anchors_found.append(keyword)
    anchor_score = min(10, len(anchors_found) * 2)
    checks["document_anchors"] = {
        "score": anchor_score,
        "max": 10,
        "detail": f"Found: {', '.join(anchors_found[:5])}" if anchors_found else "None",
    }
    if not anchors_found and file_type in ("pdf", "excel"):
        issues.append("No document anchors (bank name, statement keywords) found")
    total_score += anchor_score

    if original_content and file_type in ("pdf", "image") and total_score < _QUALITY_PASS_THRESHOLD:
        ai_verify = _ai_visual_verify(original_content, text[:3000], file_type)
        ai_score = ai_verify.get("score", 0)
        checks["ai_visual_verify"] = {
            "score": ai_score,
            "max": 15,
            "detail": ai_verify.get("detail", ""),
        }
        issues.extend(ai_verify.get("issues", []))
    else:
        ai_score = 15 if total_score >= _QUALITY_PASS_THRESHOLD else 0
        checks["ai_visual_verify"] = {
            "score": ai_score,
            "max": 15,
            "detail": "Skipped — other checks sufficient" if ai_score else "No original content",
        }
    total_score += ai_score

    return {
        "score": total_score,
        "passed": total_score >= _QUALITY_PASS_THRESHOLD,
        "checks": checks,
        "issues": issues,
    }


def _ai_visual_verify(content: bytes, extracted_text: str, file_type: str) -> dict[str, Any]:
    try:
        import base64

        from services.llm_router import get_llm_router

        router = get_llm_router(required=False)
        if router is None:
            return {"score": 8, "detail": "No vision LLM configured", "issues": []}

        if file_type == "pdf":
            import fitz

            doc = fitz.open(stream=content, filetype="pdf")
            page = doc[0]
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img_bytes = pix.tobytes("png")
            doc.close()
            mime = "image/png"
        else:
            img_bytes = content
            mime = "image/png"

        img_b64 = base64.b64encode(img_bytes).decode()
        data = router.verify_extraction_visually(img_b64, extracted_text, mime)
        score = int(data.get("score", 0))
        if score <= 0 and data.get("match"):
            score = 12
        return {
            "score": min(15, max(0, score)),
            "detail": "AI visual verification (gemini/openai)",
            "issues": data.get("issues") or data.get("missing_sections") or [],
        }
    except Exception as exc:
        logger.warning("AI visual verify failed: %s", exc)
    return {"score": 8, "detail": "AI visual verification — fallback", "issues": []}


def _vision_read_page(img_b64: str, mime_type: str = "image/png") -> str:
    from services.llm_router import get_llm_router

    router = get_llm_router(required=False)
    if router is None:
        return ""
    return router.read_image_as_text(img_b64, mime_type)


# ── Retry cascade ─────────────────────────────────────────────────────────────


def _fast_upload_enabled() -> bool:
    return os.getenv("SMARTSPEND_FAST_UPLOAD", "1").lower() in ("1", "true", "yes")


def _is_image_extension(ext: str) -> bool:
    return ext in ("jpg", "jpeg", "png", "tiff", "bmp", "webp", "gif", "heic")


def extract_text_cascade(
    content: bytes,
    filename: str,
    *,
    fast_upload: bool | None = None,
) -> dict[str, Any]:
    """
    Multisource text extraction (same cascade as onboarding uploads) without DB writes.
    Used by AI chat uploads so images get OCR (Tesseract) + vision (Gemini/OpenAI).
    """
    use_fast = _fast_upload_enabled() if fast_upload is None else bool(fast_upload)
    ext = get_extension(filename)
    # Images / receipts: always run full cascade (OCR → vision), never fast-single-pass.
    if _is_image_extension(ext):
        use_fast = False

    methods: list[tuple[str, Callable[[], dict[str, Any]]]] = [
        ("primary", lambda: extract_text_monster(content, filename)),
        ("alternate_engine", lambda: _alternate_extraction(content, filename)),
        ("ocr_forced", lambda: _force_ocr_extraction(content, filename)),
        ("vision_api", lambda: _vision_api_extraction(content, filename)),
    ]
    if use_fast and ext in ("pdf", "csv", "xlsx", "xls", "txt", "text"):
        methods = methods[:1]

    best_result: dict[str, Any] | None = None
    best_score = 0
    fast_pass_threshold = 50

    for attempt, (method_name, extract_fn) in enumerate(methods, 1):
        try:
            result = extract_fn()
            gate = quality_gate(result, original_content=content)
            result["quality_score"] = gate["score"]
            result["quality_checks"] = gate["checks"]
            result["quality_issues"] = gate["issues"]
            result["attempt_number"] = attempt
            result["retry_method"] = method_name

            if gate["score"] > best_score:
                best_score = gate["score"]
                best_result = result

            if gate["passed"] or (use_fast and gate["score"] >= fast_pass_threshold):
                logger.info(
                    "Cascade PASSED attempt %s (%s) score=%s fast=%s file=%s",
                    attempt,
                    method_name,
                    gate["score"],
                    use_fast,
                    filename,
                )
                return best_result or result
            logger.info(
                "Cascade FAILED attempt %s (%s) score=%s issues=%s",
                attempt,
                method_name,
                gate["score"],
                gate["issues"],
            )
        except Exception as exc:
            logger.error("Cascade attempt %s (%s) crashed: %s", attempt, method_name, exc)

    if best_result:
        logger.warning("Cascade below threshold; returning best score=%s method=%s", best_score, best_result.get("method"))
        return best_result

    return {
        "text": "",
        "method": "all_failed",
        "quality_score": 0,
        "error": "All extraction methods failed. Document may need manual review.",
        "file_type": ext,
        "pages": [],
        "tables": [],
    }


def extract_with_retry(
    content: bytes,
    filename: str,
    user_id: int,
    doc_id: int,
    conn,
    *,
    fast_upload: bool | None = None,
) -> dict[str, Any]:
    """
    Monster text-extraction cascade (pdfplumber → alt engine → OCR → vision).

    ``fast_upload`` (default on via SMARTSPEND_FAST_UPLOAD): stop after the first
    good pass so signup/settings uploads finish in ~10–15s instead of running
    OCR + vision on every file.
    """
    use_fast = _fast_upload_enabled() if fast_upload is None else bool(fast_upload)
    ext = get_extension(filename)
    if _is_image_extension(ext):
        use_fast = False

    methods: list[tuple[str, Callable[[], dict[str, Any]]]] = [
        ("primary", lambda: extract_text_monster(content, filename)),
        ("alternate_engine", lambda: _alternate_extraction(content, filename)),
        ("ocr_forced", lambda: _force_ocr_extraction(content, filename)),
        ("vision_api", lambda: _vision_api_extraction(content, filename)),
    ]
    if use_fast and ext in ("pdf", "csv", "xlsx", "xls", "txt", "text"):
        methods = methods[:1]

    best_result: dict[str, Any] | None = None
    best_score = 0
    fast_pass_threshold = 50

    for attempt, (method_name, extract_fn) in enumerate(methods, 1):
        try:
            result = extract_fn()
            gate = quality_gate(result, original_content=content)
            result["quality_score"] = gate["score"]
            result["quality_checks"] = gate["checks"]
            result["quality_issues"] = gate["issues"]
            result["attempt_number"] = attempt
            result["retry_method"] = method_name

            _store_extraction_attempt(conn, doc_id, user_id, result, gate, attempt, len(content))

            if gate["score"] > best_score:
                best_score = gate["score"]
                best_result = result

            if gate["passed"] or (use_fast and gate["score"] >= fast_pass_threshold):
                logger.info(
                    "Quality gate PASSED attempt %s (%s) score=%s fast=%s",
                    attempt,
                    method_name,
                    gate["score"],
                    use_fast,
                )
                return best_result or result
            logger.info(
                "Quality gate FAILED attempt %s (%s) score=%s issues=%s",
                attempt,
                method_name,
                gate["score"],
                gate["issues"],
            )
        except Exception as exc:
            logger.error("Extraction attempt %s (%s) crashed: %s", attempt, method_name, exc)
            _store_extraction_attempt(
                conn,
                doc_id,
                user_id,
                {"text": "", "method": method_name, "file_type": get_extension(filename), "error": str(exc)},
                {"score": 0, "passed": False, "checks": {}, "issues": [str(exc)]},
                attempt,
                len(content),
            )

    if best_result:
        logger.warning("All attempts below threshold; best score=%s", best_score)
        return best_result

    return {
        "text": "",
        "method": "all_failed",
        "quality_score": 0,
        "error": "All extraction methods failed. Document may need manual review.",
        "file_type": get_extension(filename),
        "pages": [],
        "tables": [],
    }


def _alternate_extraction(content: bytes, filename: str) -> dict[str, Any]:
    ext = get_extension(filename)
    if ext == "pdf":
        try:
            import fitz

            doc = fitz.open(stream=content, filetype="pdf")
            pages = []
            all_text = []
            for i, page in enumerate(doc):
                text = page.get_text("text") or ""
                pages.append({"page": i + 1, "text": text, "method": "fitz_exclusive", "char_count": len(text)})
                all_text.append(text)
            doc.close()
            full_text = "\n".join(all_text)
            return {
                "file_type": "pdf",
                "text": full_text,
                "method": "fitz_exclusive",
                "pages": pages,
                "tables": [],
                "page_count": len(pages),
                "quality_score": 0,
            }
        except Exception as exc:
            return {"text": "", "method": "fitz_failed", "quality_score": 0, "file_type": "pdf", "pages": [], "tables": [], "error": str(exc)}
    for enc in ("latin-1", "cp1252", "iso-8859-1", "utf-16"):
        try:
            text = content.decode(enc)
            if len(text.strip()) > 100:
                return {
                    "file_type": ext,
                    "text": text,
                    "method": f"decode_{enc}",
                    "pages": [{"page": 1, "text": text, "method": f"decode_{enc}", "char_count": len(text)}],
                    "tables": [],
                    "quality_score": 0,
                }
        except Exception:
            continue
    return {"text": "", "method": "alternate_failed", "quality_score": 0, "file_type": ext, "pages": [], "tables": []}


def _force_ocr_extraction(content: bytes, filename: str) -> dict[str, Any]:
    ext = get_extension(filename)
    if ext == "pdf":
        try:
            import fitz

            doc = fitz.open(stream=content, filetype="pdf")
            pages = []
            all_text = []
            for i in range(len(doc)):
                text = _ocr_pdf_page(content, i)
                pages.append({"page": i + 1, "text": text, "method": "ocr_forced", "char_count": len(text)})
                all_text.append(text)
            doc.close()
            return {
                "file_type": "pdf",
                "text": "\n".join(all_text),
                "method": "ocr_forced",
                "pages": pages,
                "tables": [],
                "page_count": len(pages),
                "quality_score": 0,
            }
        except Exception as exc:
            return {"text": "", "method": "ocr_forced_failed", "quality_score": 0, "file_type": "pdf", "pages": [], "tables": [], "error": str(exc)}
    if ext in ("jpg", "jpeg", "png", "tiff", "bmp", "webp"):
        return _extract_image_monster(content)
    return {"text": "", "method": "ocr_not_applicable", "quality_score": 0, "file_type": ext, "pages": [], "tables": []}


def _vision_api_extraction(content: bytes, filename: str) -> dict[str, Any]:
    ext = get_extension(filename)
    try:
        import base64

        if ext == "pdf":
            import fitz

            doc = fitz.open(stream=content, filetype="pdf")
            pages = []
            all_text = []
            for i, page in enumerate(doc):
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                img_b64 = base64.b64encode(pix.tobytes("png")).decode()
                page_text = _vision_read_page(img_b64, "image/png")
                pages.append({"page": i + 1, "text": page_text, "method": "vision_api", "char_count": len(page_text)})
                all_text.append(page_text)
            doc.close()
            return {
                "file_type": "pdf",
                "text": "\n".join(all_text),
                "method": "vision_api",
                "pages": pages,
                "tables": [],
                "page_count": len(pages),
                "quality_score": 0,
            }
        mime = "image/jpeg" if ext in ("jpg", "jpeg") else "image/png"
        if ext == "webp":
            mime = "image/webp"
        img_b64 = base64.b64encode(content).decode()
        text = _vision_read_page(img_b64, mime)
        return {
            "file_type": ext,
            "text": text,
            "method": "vision_api",
            "pages": [{"page": 1, "text": text, "method": "vision_api", "char_count": len(text)}],
            "tables": [],
            "quality_score": 0,
        }
    except Exception as exc:
        return {
            "text": "",
            "method": "vision_api_failed",
            "quality_score": 0,
            "file_type": ext,
            "pages": [],
            "tables": [],
            "error": str(exc),
        }


def _store_extraction_attempt(
    conn,
    doc_id: int,
    user_id: int,
    result: dict[str, Any],
    gate: dict[str, Any],
    attempt: int,
    file_size: int,
) -> None:
    try:
        raw_text = (result.get("text") or "")[:_MAX_STORED_TEXT]
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO extraction_results
                  (uploaded_document_id, user_id, file_type, file_size_bytes, page_count,
                   raw_extracted_text, extraction_method, quality_score, quality_checks,
                   attempt_number, status, error_message)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    doc_id,
                    user_id,
                    result.get("file_type", "unknown"),
                    file_size,
                    result.get("page_count"),
                    raw_text,
                    result.get("method", "unknown"),
                    gate.get("score", 0),
                    json.dumps(gate.get("checks", {})),
                    attempt,
                    "passed" if gate.get("passed") else "failed",
                    (result.get("error") or "")[:500] or None,
                ),
            )
        conn.commit()
    except Exception as exc:
        logger.error("Failed to store extraction attempt: %s", exc)


def update_extraction_llm_result(
    conn,
    doc_id: int,
    user_id: int,
    *,
    llm_raw: str,
    model: str,
    extracted: int,
    after_validation: int,
    validation_issues: list[str],
    stored: int,
    categorization_method: str,
    status: str = "completed",
    error: str | None = None,
) -> None:
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE extraction_results
                SET llm_raw_response = %s,
                    llm_model_used = %s,
                    transactions_extracted = %s,
                    transactions_after_validation = %s,
                    validation_issues = %s,
                    transactions_stored = %s,
                    categorization_method = %s,
                    status = %s,
                    error_message = %s,
                    completed_at = NOW()
                WHERE id = (
                    SELECT id FROM extraction_results
                    WHERE uploaded_document_id = %s AND user_id = %s
                    ORDER BY attempt_number DESC, id DESC
                    LIMIT 1
                )
                """,
                (
                    (llm_raw or "")[:_MAX_STORED_TEXT],
                    model,
                    extracted,
                    after_validation,
                    json.dumps(validation_issues),
                    stored,
                    categorization_method,
                    status,
                    error,
                    doc_id,
                    user_id,
                ),
            )
        conn.commit()
    except Exception as exc:
        logger.error("Failed to update extraction LLM result: %s", exc)
