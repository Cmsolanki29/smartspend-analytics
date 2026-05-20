"""Savings math consistency — one formula for cards and dashboard rollups."""
from services.subscription_intelligence.savings_math import (
    display_savings_inr,
    estimate_cancellation_savings_inr,
    yearly_from_monthly,
)


def test_declining_with_usage_uses_seventy_percent():
    assert estimate_cancellation_savings_inr(125, 10) == 87.5
    assert estimate_cancellation_savings_inr(119, 5) == 83.3
    assert display_savings_inr(125, 10) == 87
    assert display_savings_inr(119, 5) == 83


def test_barely_used_full_cost():
    assert display_savings_inr(125, 1.5) == 125


def test_yearly_is_twelve_times_monthly():
    monthly = display_savings_inr(125, 10) + display_savings_inr(119, 5)
    assert yearly_from_monthly(monthly) == monthly * 12


def test_dashboard_totals_match_line_items():
    monthly = display_savings_inr(125, 10) + display_savings_inr(119, 5)
    assert monthly == 170
    assert yearly_from_monthly(monthly) == 2040
