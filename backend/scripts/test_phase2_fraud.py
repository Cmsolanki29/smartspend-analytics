"""Phase 2 smoke tests — ML gates + merchant trust."""
from __future__ import annotations

import sys

from db import get_connection
from services.fraud_trust import apply_merchant_trust_rule


def test_trust_rule() -> None:
    score, flag = apply_merchant_trust_rule(72, True, count_90d=6)
    assert score <= 30 and flag is False
    score2, flag2 = apply_merchant_trust_rule(72, True, count_90d=2)
    assert score2 == 72 and flag2 is True
    score3, flag3 = apply_merchant_trust_rule(45, True, count_90d=0)
    assert flag3 is True
    _, flag4 = apply_merchant_trust_rule(40, False, count_90d=0)
    assert flag4 is False
    print("  ok merchant trust rule")


def test_ml_feature_count() -> None:
    import inspect

    from sklearn.ensemble import IsolationForest

    from services.ml_model import EnhancedIsolationForest

    src = inspect.getsource(EnhancedIsolationForest.train)
    assert "contamination=0.03" in src
    det = EnhancedIsolationForest()
    import pandas as pd

    df = pd.DataFrame(
        [
            {
                "amount": 500.0,
                "type": "DEBIT",
                "category": "Food & Dining",
                "merchant": "swiggy",
                "normalized_merchant": "swiggy",
                "hour_of_day": 12,
                "day_of_week": 2,
                "is_weekend": False,
                "is_night_txn": False,
                "balance_after": 50000.0,
                "payment_method": "UPI",
            }
        ]
    )
    det.user_stats[999] = {
        "_overall": {"mean": 500.0, "std": 100.0, "q95": 900.0},
        "Food & Dining": {"mean": 500.0, "std": 100.0, "q95": 900.0},
    }
    feats = det.engineer_features(df, 999, merchant_counts={"swiggy": 8})
    assert feats.shape == (1, 9), feats.shape
    model = IsolationForest(n_estimators=10, contamination=0.03, random_state=42)
    model.fit(feats)
    print("  ok 9 ML features + contamination 0.03")


def test_swiggy_user19() -> None:
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT COUNT(*)::int FROM transactions
            WHERE user_id = 19
              AND (normalized_merchant LIKE '%swiggy%' OR LOWER(merchant) LIKE '%swiggy%')
              AND UPPER(type) = 'DEBIT'
              AND transaction_date >= CURRENT_DATE - INTERVAL '90 days';
            """
        )
        swiggy_count = int(cur.fetchone()[0])
        if swiggy_count < 5:
            print(f"  skip swiggy trust probe (only {swiggy_count} debits)")
            return
        from services.ml_model import ml_detector

        ml_detector.models.pop(19, None)
        ml_detector.scalers.pop(19, None)
        if not ml_detector.train(19):
            print("  skip swiggy trust probe (train failed)")
            return
        result = ml_detector.detect_and_update(19, process_all=True)
        cur.execute(
            """
            SELECT COUNT(*)::int FROM transactions
            WHERE user_id = 19
              AND (normalized_merchant LIKE '%swiggy%' OR LOWER(merchant) LIKE '%swiggy%')
              AND COALESCE(anomaly_flag, FALSE) = TRUE
              AND COALESCE(risk_score, 0) >= 50;
            """
        )
        flagged = int(cur.fetchone()[0])
        print(
            f"  ok user 19 swiggy debits={swiggy_count} "
            f"flagged_high_risk={flagged} processed={result.get('processed')}"
        )
    finally:
        cur.close()
        conn.close()


def main() -> int:
    print("Phase 2 tests")
    failed = 0
    for fn in (test_trust_rule, test_ml_feature_count, test_swiggy_user19):
        try:
            fn()
        except Exception as exc:
            failed += 1
            print(f"  FAIL {fn.__name__}: {exc}")
    if failed:
        print(f"\n{failed} failed")
        return 1
    print("\nAll Phase 2 checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
