"""Phase 11 — Multi-branch DNN unit + integration tests.

These tests do not require Postgres or Redis.  Database-touching paths
(trainer's ``_record_run``, hybrid scorer's full ``score`` call) are
short-circuited by monkey-patching get_pool to return None.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pytest
import torch

# Make sure we import the in-tree backend package, not anything global.
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# --------------------------------------------------------------------- #
# 1. Model architecture
# --------------------------------------------------------------------- #


def test_dnn_forward_shape_matches_branches():
    from services.phase_11_dnn.dnn_model import DNNConfig, MultiBranchDNN

    feature_dim = 18
    cfg = DNNConfig(feature_dim=feature_dim, branches=4, hidden_dim=64, dropout=0.1)
    model = MultiBranchDNN(cfg)

    x = torch.randn(7, feature_dim)
    logits = model(x)
    assert logits.shape == (7,)

    # predict_proba returns sigmoid(logits) — values in [0, 1]
    probs = model.predict_proba(x).numpy()
    assert probs.shape == (7,)
    assert np.all((probs >= 0.0) & (probs <= 1.0))


def test_dnn_branches_are_independent():
    """Each branch has its own parameter tensor — branch 0's weights must
    not be the same Python object as branch 1's weights."""
    from services.phase_11_dnn.dnn_model import DNNConfig, MultiBranchDNN

    model = MultiBranchDNN(DNNConfig(feature_dim=4, branches=3, hidden_dim=8))
    p0 = model.branches[0].net[0].weight
    p1 = model.branches[1].net[0].weight
    assert p0 is not p1


# --------------------------------------------------------------------- #
# 2. Inference: file-not-found path returns None gracefully
# --------------------------------------------------------------------- #


def test_inference_returns_none_when_disabled(monkeypatch):
    from services.phase_11_dnn import inference as dnn_inf

    dnn_inf.reset_cache()
    monkeypatch.setenv("PHASE_11_DNN_ENABLED", "false")

    # Reload settings cache so the env var actually takes effect.
    from core import config as core_cfg
    core_cfg.get_settings.cache_clear()  # type: ignore[attr-defined]

    out = dnn_inf.predict_proba({"any": "row"})
    assert out is None
    assert dnn_inf.is_enabled() is False


def test_inference_status_shape():
    from services.phase_11_dnn import inference as dnn_inf

    dnn_inf.reset_cache()
    snap = dnn_inf.status()
    assert "enabled" in snap
    assert "model_loaded" in snap
    assert "blend_weight" in snap


def test_inference_coerces_dict_in_canonical_column_order(tmp_path, monkeypatch):
    """Round-trip: write a tiny model, read it back, ensure the dict→array
    coercion respects feature_columns ordering."""
    from services.phase_11_dnn.dnn_model import DNNConfig, MultiBranchDNN
    from services.phase_11_dnn import inference as dnn_inf

    cols = ["a", "b", "c", "d"]
    model = MultiBranchDNN(DNNConfig(feature_dim=4, branches=2, hidden_dim=8))
    path = tmp_path / "tiny.pt"
    torch.save(
        {
            "state_dict": model.state_dict(),
            "config": model.cfg.to_dict(),
            "feature_columns": cols,
            "scaler": {"mean": [0.0] * 4, "std": [1.0] * 4},
            "model_version": "v_test",
        },
        str(path),
    )

    monkeypatch.setenv("PHASE_11_DNN_ENABLED", "true")
    monkeypatch.setenv("PHASE_11_DNN_MODEL_PATH", str(path))
    from core import config as core_cfg
    core_cfg.get_settings.cache_clear()  # type: ignore[attr-defined]
    dnn_inf.reset_cache()

    # Same dict in two different key-orders must produce the same prob.
    p1 = dnn_inf.predict_proba({"a": 1.0, "b": 2.0, "c": 3.0, "d": 4.0})
    p2 = dnn_inf.predict_proba({"d": 4.0, "c": 3.0, "b": 2.0, "a": 1.0})
    assert p1 is not None and p2 is not None
    assert abs(p1 - p2) < 1e-6
    assert 0.0 <= p1 <= 1.0

    # Missing column → None (not 0.0!)
    assert dnn_inf.predict_proba({"a": 1.0, "b": 2.0, "c": 3.0}) is None


def test_inference_promoted_requires_enabled(monkeypatch):
    from services.phase_11_dnn import inference as dnn_inf
    from core import config as core_cfg

    monkeypatch.setenv("PHASE_11_DNN_ENABLED", "false")
    monkeypatch.setenv("PHASE_11_DNN_PROMOTED", "true")
    core_cfg.get_settings.cache_clear()  # type: ignore[attr-defined]
    dnn_inf.reset_cache()

    # promoted=True but enabled=False → is_promoted must be False.
    assert dnn_inf.is_promoted() is False


# --------------------------------------------------------------------- #
# 3. Trainer: refuses on too-few positives
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_trainer_aborts_on_insufficient_positives(monkeypatch):
    """Force the data loader to return a labelled DataFrame with zero
    positives; trainer must abort cleanly with ``insufficient_positives``."""
    import pandas as pd

    from services.phase_11_dnn import trainer as t

    df = pd.DataFrame(
        {
            "id": range(1, 121),
            "user_id": [1] * 120,
            "amount": np.random.uniform(100, 5000, size=120),
            "merchant": ["Amazon"] * 120,
            "category": ["Shopping"] * 120,
            "payment_method": ["UPI"] * 120,
            "hour_of_day": np.random.randint(6, 22, size=120),
            "day_of_week": np.random.randint(0, 7, size=120),
            "is_weekend": [False] * 120,
            "balance_after": np.random.uniform(1000, 10000, size=120),
            "transaction_date": ["2025-01-01"] * 120,
            "type": ["DEBIT"] * 120,
            "__label__": [False] * 120,  # zero positives
            "is_fraud": [False] * 120,
        }
    )

    monkeypatch.setattr(t, "_load_transactions_df", lambda: (df, "anomaly_flag"))
    monkeypatch.setattr(t, "_record_run", lambda payload: _async_noop())

    monkeypatch.setenv("PHASE_11_MIN_POSITIVES_FOR_TRAINING", "20")
    from core import config as core_cfg
    core_cfg.get_settings.cache_clear()  # type: ignore[attr-defined]

    result = await t.run_training(epochs=2, batch_size=32)
    assert result.trained is False
    assert result.error == "insufficient_positives"


async def _async_noop():
    return None


# --------------------------------------------------------------------- #
# 4. Trainer happy path with synthetic fraud → produces a usable .pt
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_trainer_produces_usable_artifact(monkeypatch, tmp_path):
    """Train on synthetic data and confirm the saved file round-trips
    through the inference cache."""
    from services.phase_11_dnn import trainer as t
    from services.phase_11_dnn import inference as dnn_inf

    # Force synthetic path (avoid Postgres dependency).
    monkeypatch.setattr(t, "_load_transactions_df", lambda: (None, "synthetic_fraud"))
    monkeypatch.setattr(t, "_record_run", lambda payload: _async_noop())

    model_path = tmp_path / "phase11_test.pt"
    monkeypatch.setenv("PHASE_11_DNN_MODEL_PATH", str(model_path))
    monkeypatch.setenv("PHASE_11_DNN_ENABLED", "true")
    monkeypatch.setenv("PHASE_11_MIN_POSITIVES_FOR_TRAINING", "5")
    from core import config as core_cfg
    core_cfg.get_settings.cache_clear()  # type: ignore[attr-defined]
    dnn_inf.reset_cache()

    result = await t.run_training(epochs=2, batch_size=128, lr=1e-3)
    assert result.trained is True, result.error
    assert model_path.exists()
    # Sidecar JSON also written
    assert model_path.with_suffix(".json").exists()
    # Loss history monotone-ish (at least starts > 0)
    assert len(result.loss_history) >= 1
    assert result.loss_history[0] > 0.0

    # Inference cache picks it up
    snap = dnn_inf.status()
    assert snap["model_loaded"] is True
    assert snap["model_version"] == result.model_version


# --------------------------------------------------------------------- #
# 5. HybridScorer guards: DNN failure must not break scoring
# --------------------------------------------------------------------- #


def test_hybrid_scorer_imports_dnn_safely():
    """Smoke: just importing the wired hybrid scorer must not raise even
    when the DNN file does not exist."""
    from services import hybrid_scorer  # noqa: F401
    from services.phase_11_dnn import inference as dnn_inf

    dnn_inf.reset_cache()
    snap = dnn_inf.status()
    # Whatever the user's local env says, the snapshot at minimum has the flag.
    assert "enabled" in snap
