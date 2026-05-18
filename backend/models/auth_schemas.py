"""Pydantic models for authentication API."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Literal, Optional

from pydantic import AfterValidator, BaseModel, Field, field_validator, model_validator


def _validate_login_email(value: str) -> str:
    """
    email-validator rejects ``*.local`` (RFC special-use). Demo accounts may use
    ``@demo.smartspend.local`` — allow that explicitly; keep strict checks elsewhere.
    """
    s = (value or "").strip().lower()
    if not s or "@" not in s:
        raise ValueError("Invalid email address")
    local, domain = s.rsplit("@", 1)
    if not local or not domain:
        raise ValueError("Invalid email address")
    domain = domain.rstrip(".")
    if domain == "demo.smartspend.local":
        if len(local) > 80:
            raise ValueError("Invalid email address")
        if not re.fullmatch(r"[a-z0-9._+-]+", local):
            raise ValueError("Invalid email address")
        return f"{local}@{domain}"
    canonical = f"{local}@{domain}"
    try:
        from email_validator import EmailNotValidError, validate_email

        return validate_email(canonical, check_deliverability=False).normalized
    except EmailNotValidError as exc:
        raise ValueError(str(exc)) from exc


DemoFriendlyEmail = Annotated[str, AfterValidator(_validate_login_email)]


class UserSignUp(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: DemoFriendlyEmail
    password: str = Field(..., min_length=8, max_length=128)
    signup_connection: Optional[Literal["link_bank", "add_later"]] = None
    primary_bank: Optional[str] = Field(None, max_length=80)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Password must be at most 72 bytes (bcrypt limit)")
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not re.search(r"\d", v):
            raise ValueError("Password must include a number")
        if not re.search(r"[^A-Za-z0-9]", v):
            raise ValueError("Password must include a symbol")
        return v

    @model_validator(mode="after")
    def validate_signup_connection(self) -> "UserSignUp":
        sc = self.signup_connection or "add_later"
        if sc == "link_bank" and not (self.primary_bank or "").strip():
            raise ValueError("primary_bank is required when signup_connection is link_bank")
        return self


class UserSignIn(BaseModel):
    email: DemoFriendlyEmail
    password: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., min_length=10)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: int | None = None
    onboarding_required: bool = False


class AuthUserResponse(BaseModel):
    id: int
    name: str
    email: str
    monthly_income: float
    onboarding_completed: bool
    created_at: datetime
    bank: str | None = None
    dashboard_mode: str = "merged"


class PasswordReset(BaseModel):
    email: DemoFriendlyEmail


class PasswordUpdate(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8, max_length=128)
