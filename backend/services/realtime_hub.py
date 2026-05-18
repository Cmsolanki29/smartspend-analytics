"""Per-user WebSocket hub — broadcasts data_updated to connected clients only."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class RealtimeHub:
    def __init__(self) -> None:
        self._rooms: dict[int, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, user_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._rooms.setdefault(int(user_id), set()).add(websocket)
        logger.debug("ws connected user_id=%s room_size=%s", user_id, len(self._rooms.get(int(user_id), ())))

    async def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        async with self._lock:
            room = self._rooms.get(int(user_id))
            if not room:
                return
            room.discard(websocket)
            if not room:
                self._rooms.pop(int(user_id), None)

    async def broadcast(self, user_id: int, event: str, payload: dict[str, Any]) -> int:
        """Send event to all sockets in user room. Returns delivery count."""
        async with self._lock:
            sockets = list(self._rooms.get(int(user_id), set()))
        if not sockets:
            return 0
        body = json.dumps({"event": event, **payload})
        delivered = 0
        dead: list[WebSocket] = []
        for ws in sockets:
            try:
                await ws.send_text(body)
                delivered += 1
            except Exception:  # noqa: BLE001
                dead.append(ws)
        if dead:
            async with self._lock:
                room = self._rooms.get(int(user_id))
                if room:
                    for ws in dead:
                        room.discard(ws)
        return delivered

    async def emit_data_updated(self, user_id: int, source_name: str) -> int:
        return await self.broadcast(
            user_id,
            "data_updated",
            {"user_id": int(user_id), "source_name": str(source_name or "Statement")},
        )


realtime_hub = RealtimeHub()


def emit_data_updated_sync(user_id: int, source_name: str) -> None:
    """Callable from sync upload routes (documents, pipeline)."""
    payload_user = int(user_id)
    source = str(source_name or "Statement")

    async def _run() -> None:
        await realtime_hub.emit_data_updated(payload_user, source)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_run())
    except RuntimeError:
        try:
            asyncio.run(_run())
        except Exception as exc:  # noqa: BLE001
            logger.debug("emit_data_updated_sync skipped: %s", exc)
