"""OTP demo routes for onboarding mobile verification."""

from __future__ import annotations

import random

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from db import get_connection

router = APIRouter(prefix="/otp", tags=["OTP"])


class SendOTPRequest(BaseModel):
    mobile_number: str = Field(..., min_length=10, max_length=15)


class VerifyOTPRequest(BaseModel):
    mobile_number: str = Field(..., min_length=10, max_length=15)
    otp_code: str = Field(..., min_length=6, max_length=6)


@router.post("/send")
async def send_otp(data: SendOTPRequest) -> dict[str, int | str | bool]:
    """
    Generate and 'send' OTP (mock - stored in DB).
    For demo only: returns OTP in response.
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        otp_code = str(random.randint(100000, 999999))
        cur.execute(
            """
            INSERT INTO otp_verifications (mobile_number, otp_code, expires_at, verified)
            VALUES (%s, %s, NOW() + INTERVAL '5 minutes', FALSE)
            """,
            (data.mobile_number, otp_code),
        )
        conn.commit()
        return {
            "success": True,
            "message": "OTP sent successfully",
            "otp_code": otp_code,  # demo-only
            "expires_in": 300,
        }
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    finally:
        cur.close()
        conn.close()


@router.post("/verify")
async def verify_otp(data: VerifyOTPRequest) -> dict[str, str | bool]:
    """
    Verify OTP against the latest row for this mobile.

    Expiry and code checks run entirely in PostgreSQL (no Python datetime compares).
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE otp_verifications AS ov
            SET verified = TRUE
            WHERE ov.id = (
                SELECT id
                FROM otp_verifications
                WHERE mobile_number = %s
                  AND verified = FALSE
                  AND NOT (expires_at < NOW())
                  AND otp_code::text = %s
                ORDER BY created_at DESC
                LIMIT 1
            )
            RETURNING ov.id
            """,
            (data.mobile_number, data.otp_code),
        )
        updated = cur.fetchone()
        if updated:
            # Do not UPDATE users here: OTP runs before mobile is stored on the user row,
            # and older deployments used a non-existent `phone` column. `otp_verifications.verified`
            # is the source of truth; link-bank sets mobile_number + is_verified by user id.
            conn.commit()
            return {
                "success": True,
                "message": "OTP verified successfully",
                "mobile_number": data.mobile_number,
            }

        cur.execute(
            """
            SELECT
                verified,
                (expires_at < NOW()) AS is_expired,
                (otp_code::text = %s) AS code_ok
            FROM otp_verifications
            WHERE mobile_number = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (data.otp_code, data.mobile_number),
        )
        row2 = cur.fetchone()
        conn.rollback()

        if not row2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No OTP found for this number",
            )
        verified, is_expired, code_ok = bool(row2[0]), bool(row2[1]), bool(row2[2])
        if verified:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP already used")
        if is_expired:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP expired")
        if not code_ok:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OTP")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP verification failed",
        )
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    finally:
        cur.close()
        conn.close()
