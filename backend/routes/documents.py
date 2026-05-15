"""
Document upload & connected-sources API.

Endpoints:
  POST /documents/upload           — upload PDF/CSV/XLSX, extract transactions
  GET  /documents/history          — list past uploads for a user
  GET  /sources/connected           — list connected_sources + dashboard_mode for user_id
  POST /sources/connected         — add a connected source manually
  POST /sources/toggle-visibility  — JSON, query, or form (multipart/urlencoded)
  POST /user/update-dashboard-mode — JSON, query, or form
"""
from __future__ import annotations

import json
import logging
from typing import Any, Literal, Optional
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field, ValidationError, field_validator

from db import get_db
from services.dashboard_scope import normalize_dashboard_mode
from services.pdf_parser import PDFParserAgent

logger = logging.getLogger(__name__)
router = APIRouter(tags=["documents"])


class ToggleVisibilityBody(BaseModel):
    user_id: int
    source_id: int
    visible: bool

    @field_validator("user_id", "source_id", mode="before")
    @classmethod
    def _coerce_int_ids(cls, v):
        if isinstance(v, bool):
            raise ValueError("expected integer id")
        if isinstance(v, int):
            return v
        if isinstance(v, str) and v.strip().lstrip("-").isdigit():
            return int(v)
        return v

    @field_validator("visible", mode="before")
    @classmethod
    def _coerce_visible(cls, v):
        if isinstance(v, str):
            return v.strip().lower() in ("1", "true", "yes", "on")
        return bool(v)


class DashboardModeBody(BaseModel):
    user_id: int
    mode: Literal["bank_only", "credit_card_only", "merged"]
    visible_source_ids: list[int] = Field(default_factory=list)

    @field_validator("user_id", mode="before")
    @classmethod
    def _coerce_user_id(cls, v):
        if isinstance(v, bool):
            raise ValueError("expected integer user_id")
        if isinstance(v, int):
            return v
        if isinstance(v, str) and v.strip().lstrip("-").isdigit():
            return int(v)
        return v

    @field_validator("mode", mode="before")
    @classmethod
    def _normalize_mode(cls, v):
        s = (str(v) if v is not None else "").strip().lower()
        aliases = {
            "card_only": "credit_card_only",
            "cards_only": "credit_card_only",
            "credit_card": "credit_card_only",
            "cc_only": "credit_card_only",
            "bank": "bank_only",
            "merged_view": "merged",
            "both": "merged",
        }
        return aliases.get(s, s)

    @field_validator("visible_source_ids", mode="before")
    @classmethod
    def _coerce_source_id_list(cls, v: Any) -> list[int]:
        if v is None:
            return []
        if isinstance(v, str):
            out: list[int] = []
            for part in v.split(","):
                p = part.strip()
                if p.lstrip("-").isdigit():
                    out.append(int(p))
            return out
        out = []
        for item in v:
            if isinstance(item, bool):
                continue
            if isinstance(item, int):
                out.append(item)
            elif isinstance(item, float) and item == int(item):
                out.append(int(item))
            elif isinstance(item, str) and item.strip().lstrip("-").isdigit():
                out.append(int(item.strip()))
        return out


_parser = PDFParserAgent()


async def _merge_toggle_fields(request: Request) -> dict[str, Any]:
    """Merge user_id, source_id, visible from query, multipart/form, urlencoded body, or JSON."""
    out: dict[str, Any] = {}
    for k in ("user_id", "source_id", "visible"):
        v = request.query_params.get(k)
        if v is not None and str(v).strip() != "":
            out[k] = v

    ct = (request.headers.get("content-type") or "").lower()

    if "multipart/form-data" in ct or "application/x-www-form-urlencoded" in ct:
        try:
            form = await request.form()
            for k in ("user_id", "source_id", "visible"):
                if k not in out or str(out.get(k, "")).strip() == "":
                    fv = form.get(k)
                    if fv is not None and str(fv).strip() != "":
                        out[k] = fv
        except Exception:
            pass
        return out

    raw = await request.body()
    if not raw:
        return out

    if "application/json" in ct or ct.endswith("+json") or raw.lstrip().startswith(b"{"):
        try:
            jd = json.loads(raw.decode("utf-8"))
            if isinstance(jd, dict):
                for k in ("user_id", "source_id", "visible"):
                    if k not in out or str(out.get(k, "")).strip() == "":
                        if k in jd and jd[k] is not None and str(jd[k]).strip() != "":
                            out[k] = jd[k]
        except json.JSONDecodeError:
            pass

    if ("application/x-www-form-urlencoded" in ct) or (b"=" in raw and b"&" in raw):
        try:
            flat = {
                kk: vv[0]
                for kk, vv in parse_qs(raw.decode("utf-8"), keep_blank_values=False).items()
                if vv
            }
            for k in ("user_id", "source_id", "visible"):
                if k not in out or str(out.get(k, "")).strip() == "":
                    if flat.get(k) not in (None, ""):
                        out[k] = flat[k]
        except Exception:
            pass

    return out


async def _merge_dashboard_fields(request: Request) -> dict[str, Any]:
    """Merge user_id, mode, visible_source_ids from query, form, urlencoded, or JSON."""
    out: dict[str, Any] = {}
    for k in ("user_id", "mode", "visible_source_ids"):
        v = request.query_params.get(k)
        if v is not None and str(v).strip() != "":
            out[k] = v

    ct = (request.headers.get("content-type") or "").lower()

    if "multipart/form-data" in ct or "application/x-www-form-urlencoded" in ct:
        try:
            form = await request.form()
            for k in ("user_id", "mode", "visible_source_ids"):
                if k not in out or str(out.get(k, "")).strip() == "":
                    fv = form.get(k)
                    if fv is not None and str(fv).strip() != "":
                        out[k] = fv
        except Exception:
            pass
        return out

    raw = await request.body()
    if not raw:
        return out

    if "application/json" in ct or ct.endswith("+json") or raw.lstrip().startswith(b"{"):
        try:
            jd = json.loads(raw.decode("utf-8"))
            if isinstance(jd, dict):
                for k in ("user_id", "mode", "visible_source_ids"):
                    if k not in out or str(out.get(k, "")).strip() == "":
                        if k in jd and jd[k] is not None:
                            if k == "visible_source_ids":
                                out[k] = jd[k]
                            elif str(jd[k]).strip() != "":
                                out[k] = jd[k]
        except json.JSONDecodeError:
            pass

    if ("application/x-www-form-urlencoded" in ct) or (b"=" in raw and b"&" in raw):
        try:
            flat = {
                kk: vv[0]
                for kk, vv in parse_qs(raw.decode("utf-8"), keep_blank_values=False).items()
                if vv
            }
            for k in ("user_id", "mode", "visible_source_ids"):
                if k not in out or str(out.get(k, "")).strip() == "":
                    if flat.get(k) not in (None, ""):
                        out[k] = flat[k]
        except Exception:
            pass

    return out


async def _toggle_payload_from_request(request: Request) -> ToggleVisibilityBody:
    """Query + JSON + x-www-form-urlencoded + multipart (form fields)."""
    merged = await _merge_toggle_fields(request)
    try:
        return ToggleVisibilityBody.model_validate(merged)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=(
                "Need user_id, source_id, and visible (bool). "
                "Send as query params, JSON body, or form fields. "
                f"Got keys: {list(merged.keys())}. Validation: {exc.errors()}"
            ),
        ) from exc


async def _dashboard_payload_from_request(request: Request) -> DashboardModeBody:
    """Query + JSON + form; visible_source_ids optional (list or comma string)."""
    merged = await _merge_dashboard_fields(request)
    if "visible_source_ids" not in merged:
        merged["visible_source_ids"] = ""
    try:
        return DashboardModeBody.model_validate(merged)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=(
                "Need user_id and mode (bank_only | credit_card_only | merged). "
                "Optional visible_source_ids as list or comma-separated string. "
                f"Got keys: {list(merged.keys())}. Validation: {exc.errors()}"
            ),
        ) from exc


_ALLOWED_EXTENSIONS = {"pdf", "csv", "xlsx", "xls", "txt"}
_MAX_FILE_MB = 20


# ──────────────────────────────────────────────────────────────────────────────
# POST /documents/upload
# ──────────────────────────────────────────────────────────────────────────────
@router.post("/documents/upload")
async def upload_statement(
    file: UploadFile = File(...),
    user_id: int = Form(...),
    source_type: str = Form(...),
    institution_name: str = Form(...),
    account_number_masked: Optional[str] = Form(None),
    conn=Depends(get_db),
):
    """Upload bank/credit-card statement PDF or CSV and extract transactions."""

    raw = (source_type or "").strip().lower()
    syn = {"bank_statement": "bank_statement_pdf", "bank_stmt": "bank_statement_pdf", "statement": "bank_statement_pdf"}
    raw = syn.get(raw, raw)
    allowed = {"bank", "credit_card", "upi", "other", "bank_statement_pdf"}
    if raw not in allowed:
        raise HTTPException(status_code=400, detail="Invalid source_type")

    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '.{ext}' not supported. Use PDF, CSV, or XLSX.",
        )

    file_bytes = await file.read()

    size_kb = len(file_bytes) // 1024
    if size_kb > _MAX_FILE_MB * 1024:
        raise HTTPException(status_code=413, detail=f"File too large (max {_MAX_FILE_MB} MB).")

    safe_name = (file.filename or "upload")[:200]
    logger.warning(
        "[upload] start user_id=%s source_type=%s institution=%r file=%r ext=%s size_kb=%s",
        user_id,
        raw,
        (institution_name or "")[:80],
        safe_name,
        ext,
        size_kb,
    )

    source_id = _upsert_source(
        conn,
        user_id=user_id,
        source_type=raw,
        institution_name=institution_name.strip()[:100],
        account_number_masked=account_number_masked,
    )

    doc_id = _create_document_record(
        conn,
        user_id=user_id,
        source_id=source_id,
        filename=file.filename or "upload",
        file_type=ext,
        size_kb=size_kb,
    )
    conn.commit()

    try:
        logger.warning(
            "[upload] extract begin document_id=%s connected_source_id=%s bytes=%s",
            doc_id,
            source_id,
            len(file_bytes),
        )
        result = _parser.extract_transactions(
            file_bytes=file_bytes,
            filename=file.filename or "upload",
            user_id=user_id,
            document_id=doc_id,
            connected_source_id=source_id,
            conn=conn,
        )
    except Exception as exc:
        logger.exception(
            "[upload] extract failed document_id=%s source_id=%s user_id=%s",
            doc_id,
            source_id,
            user_id,
        )
        PDFParserAgent._mark_failed(conn, doc_id, f"{type(exc).__name__}: {exc!s}"[:400])
        conn.commit()
        detail = f"Import failed ({type(exc).__name__}): {exc}"
        if any(
            s in detail.lower()
            for s in ("undefinedcolumn", "column", "relation", "does not exist")
        ):
            detail += " If this is schema drift, run: cd backend && python -m scripts.apply_migrations (028–029)."
        raise HTTPException(status_code=500, detail=detail[:900]) from exc

    result["document_id"] = doc_id
    result["source_id"] = source_id
    logger.warning(
        "[upload] ok document_id=%s source_id=%s success=%s imported=%s",
        doc_id,
        source_id,
        result.get("success"),
        result.get("imported"),
    )
    return result


# ──────────────────────────────────────────────────────────────────────────────
# GET /documents/history
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/documents/history")
def get_upload_history(user_id: int = Query(...), conn=Depends(get_db)):
    """Return last 20 uploads for a user."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              ud.id, ud.file_name, ud.file_type, ud.file_size_kb,
              ud.extraction_status, ud.rows_extracted, ud.rows_imported,
              ud.rows_skipped_duplicates, ud.uploaded_at, ud.processed_at,
              cs.institution_name, cs.source_type
            FROM uploaded_documents ud
            LEFT JOIN connected_sources cs ON cs.id = ud.connected_source_id
            WHERE ud.user_id = %s
            ORDER BY ud.uploaded_at DESC
            LIMIT 20
            """,
            (user_id,),
        )
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]

    for r in rows:
        if r.get("uploaded_at"):
            r["uploaded_at"] = r["uploaded_at"].isoformat()
        if r.get("processed_at"):
            r["processed_at"] = r["processed_at"].isoformat()

    return {"uploads": rows}


# ──────────────────────────────────────────────────────────────────────────────
# GET /sources/connected
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/sources/connected")
def get_connected_sources(request: Request, conn=Depends(get_db)):
    """Return all active connected sources with upload & transaction counts."""
    raw_uid = request.query_params.get("user_id")
    if raw_uid is None or str(raw_uid).strip() == "":
        raise HTTPException(status_code=422, detail="Query parameter user_id is required")
    try:
        user_id = int(str(raw_uid).strip())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Query parameter user_id must be an integer") from exc
    if user_id < 1:
        raise HTTPException(status_code=422, detail="Query parameter user_id must be positive")

    with conn.cursor() as cur:
        cur.execute(
            "SELECT COALESCE(dashboard_mode, 'merged') FROM users WHERE id = %s",
            (user_id,),
        )
        dm_row = cur.fetchone()
        dashboard_mode = normalize_dashboard_mode(str(dm_row[0] if dm_row else "merged"))

        cur.execute(
            """
            SELECT
              cs.id,
              cs.source_type,
              cs.institution_name,
              cs.account_number_masked,
              cs.is_primary,
              cs.status,
              cs.connected_at,
              cs.is_visible_on_dashboard,
              cs.added_via,
              (SELECT COUNT(DISTINCT ud.id) FROM uploaded_documents ud
               WHERE ud.connected_source_id = cs.id) AS uploads_count,
              (SELECT COUNT(DISTINCT t.id) FROM transactions t
               WHERE t.connected_source_id = cs.id) AS transactions_count,
              (SELECT MAX(ud2.uploaded_at) FROM uploaded_documents ud2
               WHERE ud2.connected_source_id = cs.id) AS last_upload
            FROM connected_sources cs
            WHERE cs.user_id = %s AND cs.status = 'active'
            ORDER BY cs.is_primary DESC, cs.connected_at DESC
            """,
            (user_id,),
        )
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]

    for r in rows:
        if r.get("connected_at"):
            r["connected_at"] = r["connected_at"].isoformat()
        if r.get("last_upload"):
            r["last_upload"] = r["last_upload"].isoformat()

    return {"sources": rows, "dashboard_mode": dashboard_mode}


# ──────────────────────────────────────────────────────────────────────────────
# POST /sources/connected
# ──────────────────────────────────────────────────────────────────────────────
@router.post("/sources/connected")
def add_connected_source(
    user_id: int = Form(...),
    source_type: str = Form(...),
    institution_name: str = Form(...),
    account_number_masked: Optional[str] = Form(None),
    is_primary: bool = Form(False),
    conn=Depends(get_db),
):
    source_id = _upsert_source(
        conn,
        user_id=user_id,
        source_type=source_type,
        institution_name=institution_name.strip()[:100],
        account_number_masked=account_number_masked,
        is_primary=is_primary,
    )
    conn.commit()
    return {"success": True, "source_id": source_id}


# ──────────────────────────────────────────────────────────────────────────────
# POST /sources/toggle-visibility  (query OR JSON — fixes old/new client + proxy mismatches)
# ──────────────────────────────────────────────────────────────────────────────
@router.post("/sources/toggle-visibility")
async def toggle_source_visibility(request: Request, conn=Depends(get_db)):
    body = await _toggle_payload_from_request(request)
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE connected_sources
            SET is_visible_on_dashboard = %s
            WHERE id = %s AND user_id = %s
            RETURNING id
            """,
            (body.visible, body.source_id, body.user_id),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Source not found")
    conn.commit()
    return {"success": True, "source_id": body.source_id, "is_visible_on_dashboard": body.visible}


# ──────────────────────────────────────────────────────────────────────────────
# POST /user/set-dashboard-mode  — called at end of signup SourceSelection
# Sets dashboard_mode + marks onboarding_completed = TRUE + optional bank link
# ──────────────────────────────────────────────────────────────────────────────
@router.post("/user/set-dashboard-mode")
async def set_dashboard_mode_onboarding(request: Request, conn=Depends(get_db)):
    """
    Used exclusively by the post-signup SourceSelection screen.
    Accepts query-params or JSON body: { user_id, dashboard_mode, bank_name? }
    Marks onboarding_completed = TRUE so App.jsx routes to dashboard.
    """
    try:
        raw = await request.body()
        body_json: dict = json.loads(raw) if raw else {}
    except Exception:
        body_json = {}

    def _qp(key: str, fallback: str = "") -> str:
        v = request.query_params.get(key, "")
        return v or body_json.get(key, fallback)

    user_id_raw = _qp("user_id")
    if not user_id_raw:
        raise HTTPException(status_code=400, detail="user_id required")
    try:
        user_id = int(user_id_raw)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="user_id must be an integer")

    dashboard_mode = _qp("dashboard_mode", "bank_only").strip().lower()
    if dashboard_mode not in ("bank_only", "credit_card_only", "merged", "upload_only"):
        dashboard_mode = "bank_only"

    bank_name = _qp("bank_name", "").strip() or None
    onboarding_source = _qp("onboarding_source", "skipped").strip() or "skipped"

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE users
            SET dashboard_mode = %s,
                onboarding_completed = TRUE,
                onboarding_source = %s
            WHERE id = %s
            RETURNING id
            """,
            (dashboard_mode, onboarding_source, user_id),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="User not found")

        if bank_name:
            cur.execute(
                "SELECT id FROM bank_connections WHERE user_id = %s AND bank_name = %s",
                (user_id, bank_name),
            )
            if not cur.fetchone():
                cur.execute(
                    """
                    INSERT INTO bank_connections (user_id, bank_name, account_masked)
                    VALUES (%s, %s, '****0000')
                    ON CONFLICT DO NOTHING
                    """,
                    (user_id, bank_name),
                )

    conn.commit()
    return {"success": True, "dashboard_mode": dashboard_mode, "onboarding_completed": True}


# ──────────────────────────────────────────────────────────────────────────────
# POST /user/update-dashboard-mode  (query OR JSON)
# ──────────────────────────────────────────────────────────────────────────────
@router.post("/user/update-dashboard-mode")
async def update_dashboard_mode(request: Request, conn=Depends(get_db)):
    body = await _dashboard_payload_from_request(request)
    mode_n = body.mode.strip().lower()
    ids = list(body.visible_source_ids or [])

    with conn.cursor() as cur:
        cur.execute(
            "UPDATE users SET dashboard_mode = %s WHERE id = %s RETURNING id",
            (mode_n, body.user_id),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="User not found")

        if ids:
            cur.execute(
                "UPDATE connected_sources SET is_visible_on_dashboard = FALSE WHERE user_id = %s",
                (body.user_id,),
            )
            cur.execute(
                """
                UPDATE connected_sources
                SET is_visible_on_dashboard = TRUE
                WHERE user_id = %s AND id = ANY(%s::int[])
                """,
                (body.user_id, ids),
            )
        else:
            cur.execute(
                """
                UPDATE connected_sources
                SET is_visible_on_dashboard = TRUE
                WHERE user_id = %s AND status = 'active'
                """,
                (body.user_id,),
            )

    conn.commit()
    return {"success": True, "mode": mode_n, "visible_source_ids": ids}


# ──────────────────────────────────────────────────────────────────────────────
# Private helpers
# ──────────────────────────────────────────────────────────────────────────────
def _upsert_source(
    conn,
    *,
    user_id: int,
    source_type: str,
    institution_name: str,
    account_number_masked: str | None = None,
    is_primary: bool = False,
) -> int:
    """Insert or return existing connected_source id."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO connected_sources
              (user_id, source_type, institution_name, account_number_masked, is_primary,
               is_visible_on_dashboard, added_via, status)
            VALUES (%s, %s, %s, %s, %s, TRUE, 'settings_upload', 'active')
            ON CONFLICT ON CONSTRAINT connected_sources_user_inst_type_key DO UPDATE
              SET account_number_masked = COALESCE(EXCLUDED.account_number_masked, connected_sources.account_number_masked),
                  status = 'active'
            RETURNING id
            """,
            (user_id, source_type, institution_name, account_number_masked, is_primary),
        )
        return cur.fetchone()[0]


def _create_document_record(
    conn, *, user_id: int, source_id: int, filename: str, file_type: str, size_kb: int
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO uploaded_documents
              (user_id, connected_source_id, file_name, file_type, file_size_kb)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (user_id, source_id, filename, file_type, size_kb),
        )
        return cur.fetchone()[0]
