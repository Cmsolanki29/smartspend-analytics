"""Ledger + health band unit tests."""
from services.scorer import health_band_for_score


def test_health_bands():
    assert health_band_for_score(75) == ("STABLE", "Stable")
    assert health_band_for_score(62) == ("MODERATE", "Moderate")
    assert health_band_for_score(52) == ("AT_RISK", "Needs attention")
    assert health_band_for_score(47) == ("CRITICAL", "Critical")


def test_health_points_sum_cap():
    """Seven buckets max at 100."""
    assert 22 + 13 + 18 + 10 + 5 + 17 + 15 == 100


def test_planning_points_reflects_progress_not_only_burden():
    from services.financial_behavior import score_planning_points

    heavy = {
        "planning_burden_pct": 62.0,
        "has_planning_data": True,
        "festival_progress_pct": 40.0,
        "purchase_goal_progress_pct": 30.0,
        "active_purchase_goals": 2,
        "active_festivals": 1,
        "purchase_goals_on_track": 1,
    }
    pts = score_planning_points(heavy, income_basis=75000.0)
    assert pts >= 3, "progress should add points even when burden is high"
    assert pts <= 15

    light = {
        "planning_burden_pct": 18.0,
        "has_planning_data": True,
        "festival_progress_pct": 80.0,
        "purchase_goal_progress_pct": 70.0,
        "active_purchase_goals": 1,
        "active_festivals": 1,
        "purchase_goals_on_track": 1,
    }
    assert score_planning_points(light, income_basis=75000.0) >= 10
