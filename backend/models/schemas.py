"""Pydantic v2 request/response models for SmartSpend API."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Optional

from pydantic import BaseModel, Field


class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    monthly_income: float
    savings_goal: float
    risk_tolerance: str


class TransactionResponse(BaseModel):
    id: int
    user_id: int
    transaction_date: date
    transaction_time: time
    amount: float
    type: str
    description: Optional[str] = None
    merchant: Optional[str] = None
    category: Optional[str] = None
    payment_method: Optional[str] = None
    anomaly_flag: bool
    risk_score: int
    risk_level: str
    anomaly_reason: Optional[str] = None
    # Source info — populated by list_transactions (NULL for seed/demo rows)
    source_name: Optional[str] = None
    source_type: Optional[str] = None


class SpendingAnalysis(BaseModel):
    category: str
    total_amount: float
    transaction_count: int
    percentage: float
    avg_transaction: float
    trend: str


class AnomalyResponse(BaseModel):
    transaction_id: int
    merchant: str
    amount: float
    transaction_date: date
    anomaly_type: str
    risk_score: int
    risk_level: str
    reason: str


class HealthScoreResponse(BaseModel):
    score: Optional[int] = Field(default=None, ge=0, le=100)
    grade: str = ""
    components: dict[str, Any] = Field(default_factory=dict)
    trend: str = "STABLE"
    health_band: str = "UNKNOWN"
    health_label: str = "—"
    recommendations: list[str] = Field(default_factory=list)
    savings_rate: Optional[float] = None
    reason: Optional[str] = None
    message: Optional[str] = None
    days_needed: Optional[int] = None
    days_available: Optional[int] = None
    mode: Optional[str] = None


class InsightResponse(BaseModel):
    summary: str
    key_insights: list[str]
    warnings: list[str]
    recommendations: list[str]
    generated_at: datetime


class MonthlyTrend(BaseModel):
    month: str
    income: float
    expense: float
    saved: float
    health_score: int
    anomaly_count: int


class DashboardSummary(BaseModel):
    user: UserResponse
    current_month: dict[str, Any]
    health_score: HealthScoreResponse
    recent_anomalies: list[AnomalyResponse]
    spending_by_category: list[SpendingAnalysis]
    monthly_trends: list[MonthlyTrend]
    unread_alerts: int
    # Live freshness signals (used by the dashboard greeting / status pill).
    # `last_synced` is MAX(bank_connections.last_synced) for the user, falling
    # back to users.last_login when no bank is linked yet. Both can be null.
    last_synced: Optional[datetime] = None
    last_login: Optional[datetime] = None
    fraud_pending_count: int = 0
    dashboard_mode: str = "merged"
    statement_period_spend: float | None = None
    statement_transaction_count: int | None = None
