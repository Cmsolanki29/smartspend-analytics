"""WebSocket — subscribe per authenticated user room."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from services.realtime_hub import realtime_hub
from utils.auth import decode_token

logger = logging.getLogger(__name__)
router = APIRouter(tags=["realtime"])


def _user_id_from_token(token: str | None) -> int | None:
    if not token or not str(token).strip():
        return None
    try:
        payload = decode_token(str(token).strip())
        uid = payload.get("user_id")
        return int(uid) if uid is not None else None
    except Exception:  # noqa: BLE001
        return None


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: int | None = Query(None),
    token: str | None = Query(None),
):
    uid = _user_id_from_token(token) or (int(user_id) if user_id else None)
    if not uid:
        await websocket.close(code=4401)
        return

    await realtime_hub.connect(uid, websocket)
    try:
        while True:
            # Keepalive / ignore client pings
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await realtime_hub.disconnect(uid, websocket)
