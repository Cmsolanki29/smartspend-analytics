"""Map UI app ids ↔ Android packages; scope intel to device_links.apps_linked only."""
from __future__ import annotations

import json
from typing import Any

from psycopg2.extensions import connection as PgConnection

# Frontend connect modal ids (subscriptionApps.js)
APP_ID_TO_PACKAGE: dict[str, str] = {
    "youtube": "com.google.android.youtube",
    "spotify": "com.spotify.music",
    "netflix": "com.netflix.mediaclient",
    "amazon_prime": "in.amazon.mShop.android.shopping",
    "hotstar": "in.startv.hotstar",
    "canva": "com.canva.editor",
    "chatgpt": "com.openai.chatgpt",
    "chatgpt_plus": "com.openai.chatgpt",
    "linkedin": "com.linkedin.android",
    "adobe": "com.adobe.reader",
    "notion": "com.notion.android",
    "perplexity": "com.perplexity.ai",
    "figma": "com.figma.mirror",
}

PACKAGE_TO_APP_ID: dict[str, str] = {}
for _aid, _pkg in APP_ID_TO_PACKAGE.items():
    if _pkg not in PACKAGE_TO_APP_ID:
        PACKAGE_TO_APP_ID[_pkg] = _aid


def normalize_app_ids(raw: list[Any] | None) -> list[str]:
    """Accept UI ids (youtube) or Android packages; return canonical UI app ids."""
    out: list[str] = []
    seen: set[str] = set()
    for item in raw or []:
        s = str(item or "").strip()
        if not s:
            continue
        if s in APP_ID_TO_PACKAGE:
            aid = s
        elif s in PACKAGE_TO_APP_ID:
            aid = PACKAGE_TO_APP_ID[s]
        elif "." in s:
            # unknown package — keep as pseudo-id keyed by package tail
            aid = s
        else:
            aid = s
        if aid not in seen:
            seen.add(aid)
            out.append(aid)
    return out


def packages_for_app_ids(app_ids: list[str]) -> list[str]:
    pkgs: list[str] = []
    seen: set[str] = set()
    for aid in app_ids:
        pkg = APP_ID_TO_PACKAGE.get(aid)
        if pkg and pkg not in seen:
            seen.add(pkg)
            pkgs.append(pkg)
        elif "." in aid and aid not in seen:
            seen.add(aid)
            pkgs.append(aid)
    return pkgs


def fetch_linked_app_ids(conn: PgConnection, user_id: int) -> list[str]:
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT apps_linked FROM device_links
            WHERE user_id = %s AND link_status = 'active'
            ORDER BY linked_at DESC LIMIT 1;
            """,
            (user_id,),
        )
        row = cur.fetchone()
        if not row:
            return []
        raw = row[0]
        if isinstance(raw, str):
            raw = json.loads(raw) if raw else []
        return normalize_app_ids(list(raw or []))
    finally:
        cur.close()


def fetch_linked_packages(conn: PgConnection, user_id: int) -> list[str]:
    return packages_for_app_ids(fetch_linked_app_ids(conn, user_id))


def has_active_device_link(conn: PgConnection, user_id: int) -> bool:
    return len(fetch_linked_app_ids(conn, user_id)) > 0


def subscription_intel_scope_sql(alias: str = "s") -> tuple[str, list[str]]:
    """SQL fragment + params for linked_app_package filter. Empty list = match nothing."""
    return f"{alias}.linked_app_package = ANY(%s::varchar[])", []


def prune_intel_outside_linked_apps(conn: PgConnection, user_id: int, app_ids: list[str]) -> None:
    """Remove usage + device-tied subscription rows not in the user's selected apps."""
    pkgs = packages_for_app_ids(app_ids)
    cur = conn.cursor()
    try:
        if pkgs:
            cur.execute(
                "DELETE FROM app_usage_signals WHERE user_id = %s AND NOT (app_package = ANY(%s::varchar[]));",
                (user_id, pkgs),
            )
            cur.execute(
                """
                DELETE FROM subscriptions
                WHERE user_id = %s
                  AND linked_app_package IS NOT NULL
                  AND length(trim(linked_app_package)) > 0
                  AND NOT (linked_app_package = ANY(%s::varchar[]));
                """,
                (user_id, pkgs),
            )
        else:
            cur.execute("DELETE FROM app_usage_signals WHERE user_id = %s;", (user_id,))
            cur.execute(
                """
                DELETE FROM subscriptions
                WHERE user_id = %s
                  AND linked_app_package IS NOT NULL
                  AND length(trim(linked_app_package)) > 0;
                """,
                (user_id,),
            )
    finally:
        cur.close()
