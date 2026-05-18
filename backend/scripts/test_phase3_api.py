"""Phase 3 smoke — user-scoped routes + realtime hub."""
from __future__ import annotations

import sys


def test_imports() -> None:
    from routes import user_scoped_api, realtime_ws
    from services.realtime_hub import realtime_hub, emit_data_updated_sync

    assert callable(user_scoped_api.fraud_alerts)
    assert callable(realtime_ws.websocket_endpoint)
    assert realtime_hub is not None
    emit_data_updated_sync(0, "test")  # no-op if no connections
    print("  ok imports")


def test_fraud_labels_util_exists() -> None:
    # frontend util documented; backend uses display_label in investigation API
    from routes.user_scoped_api import investigation_list

    assert callable(investigation_list)
    print("  ok user_scoped investigation route")


def main() -> int:
    print("Phase 3 tests")
    failed = 0
    for fn in (test_imports, test_fraud_labels_util_exists):
        try:
            fn()
        except Exception as exc:
            failed += 1
            print(f"  FAIL {fn.__name__}: {exc}")
    if failed:
        print(f"\n{failed} failed")
        return 1
    print("\nAll Phase 3 checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
