"""Authentication routes: signup, signin, refresh, logout, current user."""

from __future__ import annotations

# Demo / judge emails: see models.auth_schemas.DemoFriendlyEmail (allows @demo.smartspend.local).

import logging
import os

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from psycopg2.extensions import connection as PgConnection

from db import get_db
from models.auth_schemas import (
    AuthUserResponse,
    RefreshTokenRequest,
    TokenResponse,
    UserSignIn,
    UserSignUp,
)
from services.dashboard_scope import normalize_dashboard_mode
from utils.auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    check_login_rate_limit,
    clear_login_attempts,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user_id,
    hash_password,
    record_failed_login,
    verify_password,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


_LEGACY_JUDGE_EMAIL_SUFFIX = "@demo.smartspend.local"
_CANONICAL_JUDGE_EMAIL_SUFFIX = "@judge.smartspend.example.com"


def _signin_lookup_emails(raw_email: str) -> list[str]:
    """
    Emails to try when looking up users.signin.

    Judge demo seed rewrites legacy ``@demo.smartspend.local`` to
    ``@judge.smartspend.example.com``; users may still type the old domain.
    """
    raw = (raw_email or "").strip()
    if not raw:
        return [raw]
    out: list[str] = []
    seen_lower: set[str] = set()

    def _add(e: str) -> None:
        lo = e.lower()
        if lo not in seen_lower:
            seen_lower.add(lo)
            out.append(e)

    _add(raw)
    if raw.lower().endswith(_LEGACY_JUDGE_EMAIL_SUFFIX):
        at = raw.lower().rfind("@")
        local = raw[:at] if at > 0 else raw
        _add(f"{local}{_CANONICAL_JUDGE_EMAIL_SUFFIX}")
    return out


def _dev_auth_detail(exc: Exception, fallback: str) -> str:
    """When SMARTSPEND_DEBUG_AUTH=1, include the real error in API detail (local debugging only)."""
    if os.getenv("SMARTSPEND_DEBUG_AUTH", "").lower() not in ("1", "true", "yes"):
        return fallback
    msg = str(exc).strip()
    if not msg:
        return fallback
    return f"{fallback}: {msg[:400]}"


def _seed_new_user_transactions(user_id: int) -> None:
    """
    Optional demo seed (1000+ txns + workspace widgets).

    Off by default so new signups see an empty dashboard until they upload statements.
    Enable for judge demos: SMARTSPEND_SEED_DEMO_TXNS=1 (or SMARTSPEND_SEED_CORPUS=1).
    """
    if os.getenv("SMARTSPEND_SEED_DEMO_TXNS", "").lower() not in ("1", "true", "yes"):
        if os.getenv("SMARTSPEND_SEED_CORPUS", "").lower() not in ("1", "true", "yes"):
            logger.info("Skipping demo transaction seed for user id=%s (upload-first onboarding)", user_id)
            return

    import random

    from db import get_connection
    from services.demo_workspace_seed import seed_demo_workspace

    conn = get_connection()
    try:
        cur = conn.cursor()
        try:
            use_corpus = os.getenv("SMARTSPEND_SEED_CORPUS", "").lower() in ("1", "true", "yes")
            if use_corpus:
                from services.indian_fintech_seed.assign import assign_corpus_to_user

                n = assign_corpus_to_user(cur, user_id, count=random.randint(1000, 1500))
                if n < 500:
                    from services.new_user_transaction_seed import ensure_user_has_transactions

                    ensure_user_has_transactions(cur, user_id, min_count=1100)
            else:
                from services.new_user_transaction_seed import ensure_user_has_transactions

                ensure_user_has_transactions(cur, user_id, min_count=1100)
            seed_demo_workspace(cur, user_id)
            conn.commit()
        except Exception as seed_exc:  # noqa: BLE001
            conn.rollback()
            logger.exception(
                "Background demo seed failed for new user id=%s (account still valid): %s",
                user_id,
                seed_exc,
            )
        finally:
            cur.close()
    finally:
        conn.close()


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def signup(
    user: UserSignUp,
    request: Request,
    background_tasks: BackgroundTasks,
    conn: PgConnection = Depends(get_db),
) -> TokenResponse:
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM users WHERE lower(email) = lower(%s)", (str(user.email),))
        if cur.fetchone():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

        password_hash = hash_password(user.password)
        cur.execute(
            """
            INSERT INTO users (name, email, password_hash, monthly_income, onboarding_completed, is_verified)
            VALUES (%s, %s, %s, %s, FALSE, FALSE)
            RETURNING id
            """,
            (user.name, str(user.email).lower(), password_hash, 0),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Registration failed")
        user_id = int(row[0])

        sc = (user.signup_connection or "add_later").strip().lower()
        if sc == "link_bank":
            pb = (user.primary_bank or "").strip()[:50]
            cur.execute(
                "UPDATE users SET bank = %s, dashboard_mode = 'bank_only' WHERE id = %s",
                (pb, user_id),
            )
        else:
            cur.execute(
                "UPDATE users SET dashboard_mode = 'merged' WHERE id = %s",
                (user_id,),
            )

        try:
            from services.onboarding_seed import seed_ghost_connected_sources

            seed_ghost_connected_sources(cur, user_id)
        except Exception as ghost_exc:  # noqa: BLE001
            logger.warning("ghost source seed skipped user_id=%s: %s", user_id, ghost_exc)

        access = create_access_token(user_id=user_id, email=str(user.email))
        refresh = create_refresh_token(user_id=user_id)
        client_host = request.client.host if request.client else None
        ua = request.headers.get("user-agent", "")[:2000]

        cur.execute(
            """
            INSERT INTO sessions (user_id, token, refresh_token, expires_at, ip_address, user_agent)
            VALUES (%s, %s, %s, NOW() + (interval '1 minute' * %s), %s, %s)
            """,
            (user_id, access, refresh, ACCESS_TOKEN_EXPIRE_MINUTES, client_host, ua),
        )
        if os.getenv("SMARTSPEND_SEED_DEMO_TXNS", "").lower() in ("1", "true", "yes") or os.getenv(
            "SMARTSPEND_SEED_CORPUS", ""
        ).lower() in ("1", "true", "yes"):
            background_tasks.add_task(_seed_new_user_transactions, user_id)
            logger.info("New user registered id=%s email=%s (demo seed scheduled)", user_id, user.email)
        else:
            logger.info("New user registered id=%s email=%s (upload-first, no demo seed)", user_id, user.email)
        return TokenResponse(
            access_token=access,
            refresh_token=refresh,
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user_id=user_id,
            onboarding_required=True,
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Signup error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_dev_auth_detail(exc, "Registration failed"),
        ) from exc
    finally:
        cur.close()


@router.post("/signin", response_model=TokenResponse)
def signin(credentials: UserSignIn, request: Request, conn: PgConnection = Depends(get_db)) -> TokenResponse:
    check_login_rate_limit(str(credentials.email))
    cur = conn.cursor()
    try:
        row = None
        for email_try in _signin_lookup_emails(str(credentials.email)):
            cur.execute(
                """
                SELECT id, name, email, password_hash, onboarding_completed
                FROM users
                WHERE lower(email) = lower(%s)
                """,
                (email_try,),
            )
            row = cur.fetchone()
            if row:
                break
        if not row:
            record_failed_login(str(credentials.email))
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

        user_id, _name, email, password_hash, _onb = row[0], row[1], row[2], row[3], row[4]
        if not verify_password(credentials.password, password_hash):
            record_failed_login(str(credentials.email))
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

        clear_login_attempts(str(credentials.email))
        cur.execute("UPDATE users SET last_login = NOW() WHERE id = %s", (user_id,))

        access = create_access_token(user_id=int(user_id), email=str(email))
        refresh = create_refresh_token(user_id=int(user_id))
        client_host = request.client.host if request.client else None
        ua = request.headers.get("user-agent", "")[:2000]

        cur.execute(
            """
            INSERT INTO sessions (user_id, token, refresh_token, expires_at, ip_address, user_agent)
            VALUES (%s, %s, %s, NOW() + (interval '1 minute' * %s), %s, %s)
            """,
            (user_id, access, refresh, ACCESS_TOKEN_EXPIRE_MINUTES, client_host, ua),
        )
        logger.info("User signed in id=%s email=%s", user_id, email)
        return TokenResponse(
            access_token=access,
            refresh_token=refresh,
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Signin error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_dev_auth_detail(exc, "Login failed"),
        ) from exc
    finally:
        cur.close()


@router.get("/me", response_model=AuthUserResponse)
def get_me(user_id: int = Depends(get_current_user_id), conn: PgConnection = Depends(get_db)) -> AuthUserResponse:
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, name, email, monthly_income::float,
                   COALESCE(onboarding_completed, FALSE), created_at,
                   bank, COALESCE(dashboard_mode, 'merged')
            FROM users WHERE id = %s
            """,
            (user_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return AuthUserResponse(
            id=int(row[0]),
            name=row[1],
            email=row[2],
            monthly_income=float(row[3]),
            onboarding_completed=bool(row[4]),
            created_at=row[5],
            bank=row[6],
            dashboard_mode=normalize_dashboard_mode(str(row[7] or "merged")),
        )
    finally:
        cur.close()


@router.post("/logout", status_code=status.HTTP_200_OK)
def logout(user_id: int = Depends(get_current_user_id), conn: PgConnection = Depends(get_db)) -> dict[str, str]:
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))
        return {"message": "Logged out successfully"}
    finally:
        cur.close()


@router.post("/refresh", response_model=TokenResponse)
def refresh_tokens(body: RefreshTokenRequest, conn: PgConnection = Depends(get_db)) -> TokenResponse:
    payload = decode_token(body.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT user_id FROM sessions
            WHERE refresh_token = %s AND expires_at > NOW()
            """,
            (body.refresh_token,),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired or invalid")

        cur.execute("SELECT email FROM users WHERE id = %s", (int(user_id),))
        er = cur.fetchone()
        email = str(er[0]) if er else None

        access = create_access_token(user_id=int(user_id), email=email)
        cur.execute(
            """
            UPDATE sessions
            SET token = %s, expires_at = NOW() + (interval '1 minute' * %s)
            WHERE refresh_token = %s
            """,
            (access, ACCESS_TOKEN_EXPIRE_MINUTES, body.refresh_token),
        )
        return TokenResponse(
            access_token=access,
            refresh_token=body.refresh_token,
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
    finally:
        cur.close()


@router.get("/verify")
def verify_token(user_id: int = Depends(get_current_user_id)) -> dict[str, int]:
    """Lightweight protected route to confirm Bearer token is valid."""
    return {"user_id": user_id}
