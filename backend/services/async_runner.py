"""
Dedicated asyncio event-loop thread for sync FastAPI routes.

Avoids Windows ProactorEventLoop corruption from asyncio.run() inside request threads.
All async fraud/orchestrator calls should use ``run_coroutine()``.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, TypeVar

logger = logging.getLogger(__name__)
T = TypeVar("T")

_loop: asyncio.AbstractEventLoop | None = None
_thread: threading.Thread | None = None
_ready = threading.Event()
_lock = threading.Lock()


def _loop_thread_main() -> None:
    global _loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _loop = loop
    try:
        from core.db import init_runner_pool

        loop.run_until_complete(init_runner_pool(loop))
    except Exception as exc:  # noqa: BLE001
        logger.warning("async runner pool init failed (fraud DB may degrade): %s", exc)
    _ready.set()
    logger.info("SmartSpend async runner started")
    try:
        loop.run_forever()
    finally:
        try:
            from core.db import close_runner_pool

            loop.run_until_complete(close_runner_pool())
        except Exception:
            pass
        try:
            loop.close()
        except Exception:
            pass


def _ensure_started() -> asyncio.AbstractEventLoop:
    global _thread, _loop
    with _lock:
        if _loop is not None and _loop.is_running():
            return _loop
        _ready.clear()
        _thread = threading.Thread(
            target=_loop_thread_main,
            name="smartspend-async-runner",
            daemon=True,
        )
        _thread.start()
    if not _ready.wait(timeout=10):
        raise RuntimeError("Async runner failed to start within 10s")
    if _loop is None:
        raise RuntimeError("Async runner loop is not available")
    return _loop


def _reset_runner() -> None:
    global _loop, _thread
    with _lock:
        _loop = None
        _thread = None
    _ready.clear()


def run_coroutine(coro: Any, *, timeout: float = 45.0) -> Any:
    """Schedule *coro* on the shared background loop and block for the result."""
    for attempt in range(2):
        loop = _ensure_started()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        try:
            return future.result(timeout=timeout)
        except (RuntimeError, asyncio.InvalidStateError) as exc:
            if attempt == 0 and "loop" in str(exc).lower():
                logger.warning("async runner stale — restarting: %s", exc)
                _reset_runner()
                continue
            raise
    raise RuntimeError("async runner failed after restart")
