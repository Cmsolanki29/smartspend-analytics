"""Async PostgreSQL connection pool via asyncpg.

Phase 1: Real-time event-driven scoring.
Dependencies: asyncpg.
Performance budget: pool init at startup; individual acquires <1ms.

Why asyncpg alongside psycopg2?
  The existing psycopg2 code is sync and works; we keep it untouched.
  All new Phase 1+ code that is on the async request path uses asyncpg
  to avoid blocking the event loop.  The two pools are independent.
"""

from __future__ import annotations

import asyncio
import logging

import asyncpg

from core.config import get_settings

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None
_runner_pool: asyncpg.Pool | None = None
_runner_loop_id: int | None = None


async def _create_pool() -> asyncpg.Pool | None:
    settings = get_settings()
    try:
        pool = await asyncpg.create_pool(
            dsn=settings.DATABASE_URL,
            min_size=2,
            max_size=20,
            command_timeout=10,
            statement_cache_size=0,  # disable prepared-stmt cache for PgBouncer compat
        )
        logger.info("asyncpg pool initialised (max_size=20)")
        return pool
    except Exception as exc:
        logger.warning(
            "asyncpg pool init failed — async DB features degraded: %s", exc
        )
        return None


async def init_pool() -> None:
    """Create the asyncpg pool on the FastAPI / uvicorn event loop."""
    global _pool
    _pool = await _create_pool()


async def init_runner_pool(loop: asyncio.AbstractEventLoop) -> None:
    """Pool for sync routes that run coroutines on the background runner thread."""
    global _runner_pool, _runner_loop_id
    _runner_pool = await _create_pool()
    _runner_loop_id = id(loop)


async def close_pool() -> None:
    """Drain and close the pool.  Called in FastAPI lifespan shutdown."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("asyncpg pool closed")


async def close_runner_pool() -> None:
    global _runner_pool, _runner_loop_id
    if _runner_pool is not None:
        await _runner_pool.close()
        _runner_pool = None
        _runner_loop_id = None
        logger.info("asyncpg runner pool closed")


def get_pool() -> asyncpg.Pool:
    """Return the pool bound to the current running event loop."""
    try:
        running = asyncio.get_running_loop()
        if _runner_pool is not None and _runner_loop_id == id(running):
            return _runner_pool
    except RuntimeError:
        pass
    if _pool is None:
        raise RuntimeError(
            "asyncpg pool is not initialised. "
            "Check that init_pool() ran during startup and that DATABASE_URL is correct."
        )
    return _pool
