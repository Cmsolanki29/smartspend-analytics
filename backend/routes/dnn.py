"""Phase 11 — Multi-branch DNN admin / inspection API surface.

Endpoints (mounted at /api/risk/dnn from main.py):

  GET  /health                — feature-flag + readiness (open)
  POST /train                 — train and persist a fresh DNN (admin)
  GET  /status                — model card facts + cached load state (admin)
  GET  /runs                  — recent training runs (admin)
  POST /reload                — drop the inference cache (admin)
  GET  /shadow/evaluation     — Phase 5 segment-regression check (admin)
  POST /predict               — sandbox a single feature dict (admin)

The DNN is a SHADOW model by default: even when ``PHASE_11_DNN_ENABLED``
is true, its score never reaches end-users until ``PHASE_11_DNN_PROMOTED``
is also set.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from fastapi import APIRouter, Body, Header, HTTPException, Query

from core.config import get_settings
from core.db import get_pool
from services.monitoring.shadow_logger import shadow_logger
from services.phase_11_dnn import inference as dnn_inference
from services.phase_11_dnn.trainer import run_training

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/risk/dnn", tags=["phase-11-dnn"])


def _require_admin(
    x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
) -> None:
    expected = os.getenv("ADMIN_TOKEN", "dev-admin-secret")
    if x_admin_token != expected:
        raise HTTPException(
            status_code=403, detail="Invalid or missing X-Admin-Token header"
        )


@router.get("/health")
async def health() -> dict[str, Any]:
    """Public probe — feature flag and trained-model presence."""
    s = get_settings()
    snap = dnn_inference.status()
    return {
        "phase": 11,
        "name": "multi_branch_dnn",
        "enabled": s.PHASE_11_DNN_ENABLED,
        "promoted": s.PHASE_11_DNN_PROMOTED,
        "model_loaded": snap.get("model_loaded", False),
        "blend_weight": s.PHASE_11_DNN_BLEND_WEIGHT,
    }


@router.get("/status")
async def status(
    _admin: None = None,
    x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
) -> dict[str, Any]:
    """Full operational view: cached model + last training-run row."""
    _require_admin(x_admin_token)
    snap = dnn_inference.status()

    pool = get_pool()
    last_run: dict[str, Any] | None = None
    if pool is not None:
        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT model_version, model_path,
                           feature_dim, branches, hidden_dim, dropout,
                           n_train, n_val, n_test,
                           n_pos_train, n_pos_test, label_source,
                           epochs, batch_size, lr, pos_weight,
                           final_loss, best_val_pr_auc,
                           test_pr_auc, test_roc_auc,
                           duration_sec, error,
                           started_at, completed_at
                    FROM   dnn_training_runs
                    ORDER  BY started_at DESC
                    LIMIT  1
                    """
                )
                if row is not None:
                    last_run = dict(row)
                    for k in ("started_at", "completed_at"):
                        if last_run.get(k) is not None:
                            last_run[k] = last_run[k].isoformat()
        except Exception as exc:  # noqa: BLE001
            last_run = {"error": str(exc)}

    snap["last_run"] = last_run
    return snap


@router.get("/runs")
async def runs(
    limit: int = Query(default=20, ge=1, le=200),
    x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
) -> dict[str, Any]:
    _require_admin(x_admin_token)
    pool = get_pool()
    if pool is None:
        return {"runs": [], "note": "db_unavailable"}
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, model_version,
                       feature_dim, branches, hidden_dim,
                       n_train, n_test, n_pos_train, n_pos_test,
                       label_source,
                       final_loss, best_val_pr_auc,
                       test_pr_auc, test_roc_auc,
                       duration_sec, error,
                       started_at, completed_at
                FROM   dnn_training_runs
                ORDER  BY started_at DESC
                LIMIT  $1
                """,
                limit,
            )
        out = []
        for r in rows:
            d = dict(r)
            d["id"] = str(d["id"])
            for k in ("started_at", "completed_at"):
                if d.get(k) is not None:
                    d[k] = d[k].isoformat()
            out.append(d)
        return {"runs": out, "count": len(out)}
    except Exception as exc:  # noqa: BLE001
        return {"runs": [], "error": str(exc)}


@router.post("/train")
async def train(
    epochs: Optional[int] = Query(default=None, ge=1, le=500),
    batch_size: Optional[int] = Query(default=None, ge=8, le=4096),
    lr: Optional[float] = Query(default=None, gt=0, le=1.0),
    branches: Optional[int] = Query(default=None, ge=1, le=16),
    hidden_dim: Optional[int] = Query(default=None, ge=8, le=2048),
    dropout: Optional[float] = Query(default=None, ge=0.0, lt=1.0),
    x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
) -> dict[str, Any]:
    """Train a fresh multi-branch DNN.  Always returns a structured
    summary — even if training was aborted (e.g. ``insufficient_positives``)."""
    _require_admin(x_admin_token)
    result = await run_training(
        epochs=epochs,
        batch_size=batch_size,
        lr=lr,
        branches=branches,
        hidden_dim=hidden_dim,
        dropout=dropout,
    )
    return {
        "trained": result.trained,
        "model_version": result.model_version,
        "model_path": result.model_path,
        "label_source": result.label_source,
        "metrics": result.metrics,
        "loss_history_tail": result.loss_history[-10:],
        "val_pr_history_tail": result.val_pr_history[-10:],
        "n_train": result.n_train,
        "n_val": result.n_val,
        "n_test": result.n_test,
        "n_pos_train": result.n_pos_train,
        "n_pos_test": result.n_pos_test,
        "duration_sec": result.duration_sec,
        "error": result.error,
    }


@router.post("/reload")
async def reload_model(
    x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
) -> dict[str, Any]:
    """Drop the in-process model cache so the next prediction re-reads
    the ``.pt`` file.  Useful after manually replacing the file."""
    _require_admin(x_admin_token)
    dnn_inference.reset_cache()
    return {"reloaded": True, "snapshot": dnn_inference.status()}


@router.get("/shadow/evaluation")
async def shadow_evaluation(
    period_days: int = Query(default=7, ge=1, le=30),
    x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
) -> dict[str, Any]:
    """Run the Phase 5 segment-regression + PSI check across the last
    ``period_days`` of shadow_predictions.  Promotion is gated on this
    returning ``passed=True``."""
    _require_admin(x_admin_token)
    return await shadow_logger.evaluate_shadow(period_days=period_days)


@router.post("/predict")
async def predict(
    features: dict[str, Any] = Body(...),
    x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
) -> dict[str, Any]:
    """Sandbox endpoint: score a single feature dict.  Returns ``None``
    in ``probability`` if the DNN is disabled or unavailable — never an
    HTTP error, so the UI can show "shadow signal absent"."""
    _require_admin(x_admin_token)
    prob = dnn_inference.predict_proba(features)
    return {
        "enabled": dnn_inference.is_enabled(),
        "promoted": dnn_inference.is_promoted(),
        "probability": prob,
        "score_0_100": round(prob * 100.0, 2) if prob is not None else None,
    }
