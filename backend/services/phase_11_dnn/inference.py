"""Phase 11 DNN — synchronous online inference.

Designed to be called from inside the existing
``HybridScorer._score_with_shadow_sync`` thread-executor path.  Keeps an
in-process LRU-of-one cache so repeated calls do not re-load the
``.pt`` file from disk.

Public API:

* :func:`is_enabled` — quick feature-flag check.
* :func:`is_promoted` — True only when the admin flips the second flag,
  meaning the DNN's prediction can blend into the production score.
* :func:`predict_proba` — sync; returns ``float`` in [0, 1] or ``None``
  if the model is unavailable.
* :func:`status` — admin telemetry (model_version, last load time, etc).
* :func:`reset_cache` — invoked by the trainer after a new fit so the
  next request hot-swaps to the new weights.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np

from core.config import get_settings

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------- #
# In-process cache (one model per process)
# --------------------------------------------------------------------- #


@dataclass
class _LoadedDNN:
    model: Any                 # MultiBranchDNN
    feature_columns: list[str]
    mean: np.ndarray
    std: np.ndarray
    model_version: str
    loaded_at: datetime
    path: str


_lock = threading.Lock()
_cache: Optional[_LoadedDNN] = None
_cache_load_error: Optional[str] = None


# --------------------------------------------------------------------- #
# Public surface
# --------------------------------------------------------------------- #


def is_enabled() -> bool:
    return bool(get_settings().PHASE_11_DNN_ENABLED)


def is_promoted() -> bool:
    s = get_settings()
    return bool(s.PHASE_11_DNN_ENABLED and s.PHASE_11_DNN_PROMOTED)


def reset_cache() -> None:
    """Drop the cached model so the next ``predict_proba`` re-loads."""
    global _cache, _cache_load_error
    with _lock:
        _cache = None
        _cache_load_error = None


def status() -> dict[str, Any]:
    """Admin telemetry for ``GET /api/risk/dnn/status``."""
    s = get_settings()
    loaded = _try_load_model()  # ensures cache populated if file exists
    payload: dict[str, Any] = {
        "enabled": s.PHASE_11_DNN_ENABLED,
        "promoted": s.PHASE_11_DNN_PROMOTED,
        "blend_weight": s.PHASE_11_DNN_BLEND_WEIGHT,
        "min_positives_required": s.PHASE_11_MIN_POSITIVES_FOR_TRAINING,
        "model_path": str(Path(s.PHASE_11_DNN_MODEL_PATH).resolve()),
        "model_loaded": loaded is not None,
        "load_error": _cache_load_error,
    }
    if loaded:
        payload.update(
            {
                "model_version": loaded.model_version,
                "loaded_at": loaded.loaded_at.isoformat(),
                "feature_dim": len(loaded.feature_columns),
                "feature_columns": loaded.feature_columns,
            }
        )

        # Sidecar JSON metrics, if present.
        sidecar = Path(loaded.path).with_suffix(".json")
        if sidecar.exists():
            try:
                payload["metrics"] = json.loads(sidecar.read_text())
            except Exception:
                payload["metrics"] = None
    return payload


def predict_proba(features: Any) -> Optional[float]:
    """Return P(fraud) ∈ [0, 1] for the given feature row, or None.

    Accepts:
        * dict-like (as produced by ``feature_assembly``)
        * pandas Series
        * numpy 1-D array (must already be in canonical column order).

    Returns ``None`` whenever the DNN cannot score (disabled, missing
    file, missing columns, runtime error).  Callers must treat ``None``
    as "no shadow signal available" — never as 0.0.
    """
    if not is_enabled():
        return None

    loaded = _try_load_model()
    if loaded is None:
        return None

    try:
        import torch  # local import keeps cold-start cheap

        x = _coerce_to_array(features, loaded.feature_columns)
        if x is None:
            return None

        x_norm = (x - loaded.mean) / loaded.std
        with torch.no_grad():
            logit = loaded.model(
                torch.tensor(x_norm, dtype=torch.float32).unsqueeze(0)
            ).item()
        return float(1.0 / (1.0 + np.exp(-logit)))
    except Exception as exc:  # noqa: BLE001
        logger.warning("phase_11.dnn predict_proba failed: %s", exc)
        return None


# --------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------- #


def _try_load_model() -> Optional[_LoadedDNN]:
    global _cache, _cache_load_error
    with _lock:
        if _cache is not None:
            return _cache

        s = get_settings()
        path = Path(s.PHASE_11_DNN_MODEL_PATH).resolve()
        if not path.exists():
            _cache_load_error = f"model_file_not_found: {path}"
            return None

        try:
            import torch
            from services.phase_11_dnn.dnn_model import DNNConfig, MultiBranchDNN

            ckpt = torch.load(str(path), map_location="cpu", weights_only=False)
            cfg_dict = ckpt.get("config") or {}
            model = MultiBranchDNN(
                DNNConfig(
                    feature_dim=int(cfg_dict["feature_dim"]),
                    branches=int(cfg_dict.get("branches", 4)),
                    hidden_dim=int(cfg_dict.get("hidden_dim", 128)),
                    dropout=float(cfg_dict.get("dropout", 0.15)),
                )
            )
            model.load_state_dict(ckpt["state_dict"])
            model.eval()

            scaler = ckpt.get("scaler") or {}
            mean = np.asarray(scaler.get("mean", []), dtype=np.float32)
            std = np.asarray(scaler.get("std", []), dtype=np.float32)
            std[std < 1e-6] = 1.0

            _cache = _LoadedDNN(
                model=model,
                feature_columns=list(ckpt.get("feature_columns") or []),
                mean=mean,
                std=std,
                model_version=str(ckpt.get("model_version", "unknown")),
                loaded_at=datetime.now(timezone.utc),
                path=str(path),
            )
            _cache_load_error = None
            logger.info(
                "phase_11.dnn model loaded version=%s feature_dim=%d",
                _cache.model_version, len(_cache.feature_columns),
            )
            return _cache
        except Exception as exc:  # noqa: BLE001
            _cache_load_error = f"load_failed: {exc}"
            logger.warning("phase_11.dnn load failed: %s", exc)
            return None


def _coerce_to_array(
    features: Any,
    columns: list[str],
) -> Optional[np.ndarray]:
    """Convert assorted feature-row inputs to a 1-D float32 ndarray.

    Returns ``None`` if a required column is missing or the shape is
    wrong — caller treats this as "shadow signal unavailable".
    """
    try:
        if isinstance(features, np.ndarray):
            arr = np.asarray(features, dtype=np.float32).reshape(-1)
            if arr.shape[0] != len(columns):
                return None
            return arr

        # pandas Series / DataFrame row
        try:
            import pandas as pd  # local import — pandas is already a dep
            if isinstance(features, pd.Series):
                features = features.to_dict()
            elif isinstance(features, pd.DataFrame) and len(features) >= 1:
                features = features.iloc[0].to_dict()
        except Exception:
            pass

        if isinstance(features, dict):
            row = []
            for col in columns:
                if col not in features:
                    return None
                val = features[col]
                if val is None:
                    return None
                row.append(float(val))
            return np.asarray(row, dtype=np.float32)

        return None
    except Exception as exc:  # noqa: BLE001
        logger.debug("phase_11.dnn coerce failed: %s", exc)
        return None
