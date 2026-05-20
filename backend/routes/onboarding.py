from __future__ import annotations

import random
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from db import get_connection, get_db
from utils.auth import decode_token, get_current_user_id

router = APIRouter(prefix="/onboarding", tags=["Onboarding"])
optional_bearer = HTTPBearer(auto_error=False)

BANK_SLUG_TO_NAME: dict[str, str] = {
    "hdfc": "HDFC Bank",
    "sbi": "State Bank of India",
    "icici": "ICICI Bank",
    "axis": "Axis Bank",
    "kotak": "Kotak Mahindra",
}


class LinkBankRequest(BaseModel):
    user_id: int | None = None
    bank_name: str | None = None
    bank_slug: str | None = None
    mobile_number: str


class LinkBankDemoRequest(BaseModel):
    """Instant bank link using pre-built ghost transaction pool (signup path)."""
    bank_slug: str
    bank_name: str | None = None
    account_last4: str | None = None


def _resolve_user_id(payload_user_id: int | None, credentials: HTTPAuthorizationCredentials | None) -> int:
    if payload_user_id:
        return int(payload_user_id)
    if credentials:
        decoded = decode_token(credentials.credentials)
        resolved = decoded.get("user_id")
        if resolved:
            return int(resolved)
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="user_id is required")


def _resolve_bank_name(bank_name: str | None, bank_slug: str | None) -> str:
    if bank_name and bank_name.strip():
        return bank_name.strip()
    if bank_slug and bank_slug.strip():
        slug = bank_slug.strip().lower()
        if slug in BANK_SLUG_TO_NAME:
            return BANK_SLUG_TO_NAME[slug]
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="bank_name or bank_slug is required")


@router.get("/status")
async def get_onboarding_status(
    user_id: int | None = None,
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_bearer),
) -> dict[str, int | bool]:
    """Backward-compatible status endpoint used by existing frontend helpers."""
    resolved_user_id = _resolve_user_id(user_id, credentials)
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT COALESCE(onboarding_completed, FALSE) FROM users WHERE id = %s", (resolved_user_id,))
        row = cur.fetchone()
        onboarding_completed = bool(row[0]) if row else False

        cur.execute("SELECT COUNT(*) FROM bank_connections WHERE user_id = %s", (resolved_user_id,))
        banks_linked = int(cur.fetchone()[0])

        cur.execute("SELECT COUNT(*) FROM transactions WHERE user_id = %s", (resolved_user_id,))
        transactions_count = int(cur.fetchone()[0])

        return {
            "onboarding_completed": onboarding_completed,
            "banks_linked": banks_linked,
            "transactions_count": transactions_count,
        }
    finally:
        cur.close()
        conn.close()


@router.post("/link-bank")
async def link_bank(
    data: LinkBankRequest,
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_bearer),
) -> dict[str, Any]:
    """
    Link bank account and assign random pre-seeded transactions to user.
    Supports either:
    - body.user_id + body.bank_name (requested flow), OR
    - Bearer token + body.bank_slug (current frontend flow).
    """
    user_id = _resolve_user_id(data.user_id, credentials)
    bank_name = _resolve_bank_name(data.bank_name, data.bank_slug)
    mobile_number = data.mobile_number.strip()
    if len(mobile_number) < 10:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Valid mobile_number is required")

    conn = get_connection()
    cur = conn.cursor()
    try:
        # Check OTP FIRST before any DB writes
        cur.execute(
            """
            SELECT verified, (expires_at < NOW()) AS is_expired
            FROM otp_verifications
            WHERE mobile_number = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (mobile_number,),
        )
        otp_row = cur.fetchone()
        if not otp_row:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Send OTP first")
        otp_verified, otp_expired = otp_row[0], otp_row[1]
        if not otp_verified:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP not verified")
        if otp_expired:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP expired")

        # Check for duplicate before inserting
        cur.execute(
            "SELECT id FROM bank_connections WHERE user_id = %s AND bank_name = %s",
            (user_id, bank_name),
        )
        if cur.fetchone():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"{bank_name} is already linked to your account",
            )

        cur.execute(
            """
            INSERT INTO bank_connections (user_id, bank_name, account_masked)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (user_id, bank_name, "****1234"),
        )
        connection_row = cur.fetchone()
        connection_id = int(connection_row[0]) if connection_row else None

        cur.execute(
            """
            UPDATE users
            SET mobile_number = %s,
                is_verified = TRUE
            WHERE id = %s
            """,
            (mobile_number, user_id),
        )

        cur.execute("SELECT COUNT(*) FROM transactions WHERE user_id = %s", (user_id,))
        existing_user_txns = int(cur.fetchone()[0])

        actual_assigned = 0
        if existing_user_txns < 200:
            try:
                from services.indian_fintech_seed.assign import assign_corpus_to_user

                actual_assigned = assign_corpus_to_user(
                    cur, user_id, count=random.randint(800, 1200)
                )
            except Exception:
                actual_assigned = 0
            if actual_assigned < 200:
                try:
                    from services.new_user_transaction_seed import ensure_user_has_transactions

                    actual_assigned = ensure_user_has_transactions(
                        cur, user_id, min_count=max(200, 1000 - existing_user_txns)
                    )
                except Exception:
                    actual_assigned = 0

        cur.execute(
            """
            UPDATE users
            SET onboarding_completed = TRUE
            WHERE id = %s
            """,
            (user_id,),
        )

        conn.commit()

        return {
            "success": True,
            "connection_id": connection_id,
            "message": f"Linked {bank_name}",
            "transactions_imported": int(actual_assigned),
            "available_pool_before_assign": available_count,
        }
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    finally:
        cur.close()
        conn.close()


@router.post("/link-bank-demo")
async def link_bank_demo(
    body: LinkBankDemoRequest,
    jwt_user_id: int = Depends(get_current_user_id),
    conn=Depends(get_db),
) -> dict[str, Any]:
    """
    Signup bank linking: any bank choice gets a lifestyle pool relabeled to that bank.
    """
    from services.signup_bank_ghost_pool import link_signup_bank_ghost

    slug = (body.bank_slug or "").strip().upper()
    if not slug and not (body.bank_name or "").strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="bank_slug or bank_name is required",
        )

    cur = conn.cursor()
    try:
        cur.execute("SELECT name FROM users WHERE id = %s", (jwt_user_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        display_name = (row[0] or "You").strip() or "You"

        result = link_signup_bank_ghost(
            conn,
            cur,
            user_id=jwt_user_id,
            bank_slug=slug,
            bank_name=body.bank_name,
            display_name=display_name,
            account_last4=body.account_last4,
        )
        conn.commit()
        try:
            from services.fraud_batch_scorer import schedule_fraud_batch_score

            schedule_fraud_batch_score(jwt_user_id)
        except Exception:
            pass
        return result
    except ValueError as exc:
        conn.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        conn.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not link demo bank data",
        ) from exc
    finally:
        cur.close()


@router.get("/ghost-pool-summary")
async def ghost_pool_summary() -> dict[str, Any]:
    """Summary table of seven signup ghost pools (for docs / demo)."""
    from services.signup_bank_ghost_pool import SIGNUP_GHOST_PROFILES, ghost_pool_summary

    return {
        "count": len(SIGNUP_GHOST_PROFILES),
        "pool_user_id_range": "900001–900007",
        "bank_free": True,
        "note": "Any bank slug/name works; pools are lifestyle templates only.",
        "profiles": ghost_pool_summary(),
    }


@router.get("/banks")
async def get_banks() -> dict[str, list[dict[str, str]]]:
    """Get available banks (requested endpoint)."""
    return {
        "banks": [
            {"id": "HDFC", "name": "HDFC Bank", "logo": "🏦"},
            {"id": "SBI", "name": "State Bank of India", "logo": "🏛️"},
            {"id": "ICICI", "name": "ICICI Bank", "logo": "🏢"},
            {"id": "AXIS", "name": "Axis Bank", "logo": "🏪"},
            {"id": "KOTAK", "name": "Kotak Mahindra", "logo": "🏬"},
            {"id": "PNB", "name": "Punjab National Bank", "logo": "🏦"},
            {"id": "BOB", "name": "Bank of Baroda", "logo": "🏛️"},
        ]
    }


@router.get("/available-banks")
async def get_available_banks() -> dict[str, list[dict[str, str]]]:
    """Backward-compatible alias for existing frontend calls."""
    return await get_banks()
