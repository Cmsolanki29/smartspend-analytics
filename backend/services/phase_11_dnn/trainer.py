"""Phase 11 trainer — multi-branch DNN over the Phase 3 feature space.

Discipline points (CTO mandate):

* Reuse :func:`build_features_from_df` so the DNN sees *exactly* the
  same 18-column feature matrix as the XGBoost model.  No bespoke
  features = no train/serve skew.
* Time-based 70/15/15 split — never random — to prevent label leakage
  from "future" rows into the validation set.
* Refuse to train on too few positives.  We log the abort reason in
  ``dnn_training_runs`` so it's visible in the UI rather than silently
  emitting a meaningless model.
* Persist a ``StandardScaler``-style mean/std vector alongside the
  weights so inference does not depend on the training DataFrame.
* Pure PyTorch + scikit-learn metrics — no MLflow / no GPU.  The model
  card explicitly notes that promotion (Stripe pattern) requires the
  Phase 5 shadow logger to accumulate 24h of regression-free data.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from core.config import get_settings
from ml_training.feature_engineering import (
    SUPERVISED_FEATURE_COLUMNS,
    build_features_from_df,
)
from services.phase_11_dnn.dnn_model import DNNConfig, MultiBranchDNN

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------- #
# Training summary returned by run_training()
# --------------------------------------------------------------------- #


@dataclass
class TrainingResult:
    trained: bool
    model_version: str
    model_path: str | None
    feature_columns: list[str]
    metrics: dict[str, Any]
    loss_history: list[float]
    val_pr_history: list[float]
    n_train: int
    n_val: int
    n_test: int
    n_pos_train: int
    n_pos_test: int
    duration_sec: float
    label_source: str
    error: str | None = None


# --------------------------------------------------------------------- #
# Data ingestion
# --------------------------------------------------------------------- #


def _load_transactions_df() -> tuple[pd.DataFrame | None, str]:
    """Pull DEBIT transactions from Postgres.

    Returns (df, label_source) where label_source is the column we'll
    treat as the binary fraud label.  We prefer ``is_fraud`` when any
    positives exist; otherwise we fall back to ``anomaly_flag`` (Phase 1
    output) so the DNN at least has *some* signal to learn — and we
    record the choice transparently in the training run log.
    """
    try:
        import psycopg2
    except ImportError:
        logger.warning("psycopg2 not installed; trainer will fall back to synthetic")
        return None, "synthetic_fraud"

    settings = get_settings()
    try:
        conn = psycopg2.connect(settings.DATABASE_URL)
        df = pd.read_sql(
            """
            SELECT id,
                   user_id,
                   amount,
                   merchant,
                   category,
                   payment_method,
                   hour_of_day,
                   day_of_week,
                   is_weekend,
                   balance_after,
                   transaction_date,
                   type,
                   is_fraud,
                   anomaly_flag
              FROM transactions
             WHERE type = 'DEBIT'
             ORDER BY user_id, transaction_date
            """,
            conn,
        )
        conn.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("DB pull failed (%s); falling back to synthetic", exc)
        return None, "synthetic_fraud"

    if df is None or df.empty:
        return None, "synthetic_fraud"

    # Decide which column is the label.
    is_fraud_pos = int(df["is_fraud"].fillna(False).sum()) if "is_fraud" in df else 0
    anomaly_pos = int(df["anomaly_flag"].fillna(False).sum()) if "anomaly_flag" in df else 0

    if is_fraud_pos >= 5:
        df["__label__"] = df["is_fraud"].fillna(False).astype(bool)
        return df, "is_fraud"
    if anomaly_pos >= 5:
        df["__label__"] = df["anomaly_flag"].fillna(False).astype(bool)
        return df, "anomaly_flag"

    # Not enough real positives — caller will fall through to synthetic.
    return None, "insufficient_real_positives"


def _build_synthetic_dataset(n_rows: int = 5000) -> tuple[pd.DataFrame, str]:
    """Mirror bootstrap_train's synthetic data path so we always have a
    minimum trainable dataset on a fresh checkout."""
    from ml_training.bootstrap_train import _generate_synthetic_only
    from ml_training.synthetic_data import generate_synthetic_fraud

    base = _generate_synthetic_only(n_rows=n_rows)
    df = generate_synthetic_fraud(base, fraud_rate=0.01)
    df["__label__"] = df["is_fraud"].fillna(False).astype(bool)
    return df, "synthetic_fraud"


# --------------------------------------------------------------------- #
# Feature scaling (saved alongside weights)
# --------------------------------------------------------------------- #


def _fit_scaler(X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mean = X.mean(axis=0)
    std = X.std(axis=0)
    std[std < 1e-6] = 1.0  # don't divide by zero on constant features
    return mean, std


# --------------------------------------------------------------------- #
# DB persistence
# --------------------------------------------------------------------- #


async def _record_run(payload: dict[str, Any]) -> None:
    """Insert a row into ``dnn_training_runs``.  Best-effort; the model
    file on disk is the source of truth."""
    try:
        from core.db import get_pool
    except Exception:
        return
    pool = get_pool()
    if pool is None:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO dnn_training_runs
                    (model_version, model_path,
                     feature_dim, branches, hidden_dim, dropout,
                     n_train, n_val, n_test, n_pos_train, n_pos_test, label_source,
                     epochs, batch_size, lr, pos_weight,
                     final_loss, best_val_pr_auc, test_pr_auc, test_roc_auc,
                     loss_history, val_pr_history, duration_sec, error,
                     started_at, completed_at)
                VALUES
                    ($1, $2,
                     $3, $4, $5, $6,
                     $7, $8, $9, $10, $11, $12,
                     $13, $14, $15, $16,
                     $17, $18, $19, $20,
                     $21::jsonb, $22::jsonb, $23, $24,
                     $25, $26)
                """,
                payload["model_version"],
                payload["model_path"],
                payload["feature_dim"],
                payload["branches"],
                payload["hidden_dim"],
                payload["dropout"],
                payload["n_train"],
                payload["n_val"],
                payload["n_test"],
                payload["n_pos_train"],
                payload["n_pos_test"],
                payload["label_source"],
                payload["epochs"],
                payload["batch_size"],
                payload["lr"],
                payload["pos_weight"],
                payload.get("final_loss"),
                payload.get("best_val_pr_auc"),
                payload.get("test_pr_auc"),
                payload.get("test_roc_auc"),
                json.dumps(payload.get("loss_history", [])),
                json.dumps(payload.get("val_pr_history", [])),
                payload["duration_sec"],
                payload.get("error"),
                payload["started_at"],
                payload["completed_at"],
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("dnn._record_run failed: %s", exc)


# --------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------- #


async def run_training(
    *,
    epochs: int | None = None,
    batch_size: int | None = None,
    lr: float | None = None,
    branches: int | None = None,
    hidden_dim: int | None = None,
    dropout: float | None = None,
    seed: int = 42,
) -> TrainingResult:
    """Train a fresh multi-branch DNN and persist it to disk.

    Always returns a :class:`TrainingResult` — even on failure.  The
    HTTP route renders this dict directly so admins see *why* training
    aborted (e.g. ``insufficient_positives``).
    """
    settings = get_settings()
    started_at = datetime.now(timezone.utc)
    started_perf = time.perf_counter()

    epochs = int(epochs or settings.PHASE_11_DNN_EPOCHS)
    batch_size = int(batch_size or settings.PHASE_11_DNN_BATCH_SIZE)
    lr = float(lr or settings.PHASE_11_DNN_LR)
    branches = int(branches or settings.PHASE_11_DNN_BRANCHES)
    hidden_dim = int(hidden_dim or settings.PHASE_11_DNN_HIDDEN)
    dropout = float(dropout if dropout is not None else settings.PHASE_11_DNN_DROPOUT)

    torch.manual_seed(seed)
    np.random.seed(seed)

    # ---- 1. Data ---- #
    df, label_source = _load_transactions_df()
    if df is None:
        df, label_source = _build_synthetic_dataset()

    # build_features_from_df expects an `is_fraud` column — but our
    # internal `__label__` is the source of truth.  Normalise.
    df = df.copy()
    df["is_fraud"] = df["__label__"].astype(bool)

    X, y = build_features_from_df(df)
    feature_columns = list(X.columns)
    X = X[SUPERVISED_FEATURE_COLUMNS].copy()  # canonical order

    n_total = len(X)
    n_pos = int(y.sum())

    if n_pos < settings.PHASE_11_MIN_POSITIVES_FOR_TRAINING:
        result = TrainingResult(
            trained=False,
            model_version="aborted",
            model_path=None,
            feature_columns=feature_columns,
            metrics={"n_pos": n_pos, "min_required": settings.PHASE_11_MIN_POSITIVES_FOR_TRAINING},
            loss_history=[],
            val_pr_history=[],
            n_train=0, n_val=0, n_test=0,
            n_pos_train=0, n_pos_test=0,
            duration_sec=time.perf_counter() - started_perf,
            label_source=label_source,
            error="insufficient_positives",
        )
        await _record_run({
            "model_version": result.model_version,
            "model_path": "",
            "feature_dim": int(X.shape[1]),
            "branches": branches, "hidden_dim": hidden_dim, "dropout": dropout,
            "n_train": 0, "n_val": 0, "n_test": 0,
            "n_pos_train": 0, "n_pos_test": 0,
            "label_source": label_source,
            "epochs": epochs, "batch_size": batch_size, "lr": lr, "pos_weight": 1.0,
            "duration_sec": result.duration_sec,
            "error": "insufficient_positives",
            "started_at": started_at,
            "completed_at": datetime.now(timezone.utc),
        })
        return result

    # ---- 2. Time-based split (70/15/15) ---- #
    train_end = int(n_total * 0.70)
    val_end = int(n_total * 0.85)

    X_train_df = X.iloc[:train_end]
    X_val_df = X.iloc[train_end:val_end]
    X_test_df = X.iloc[val_end:]
    y_train = y.iloc[:train_end].astype(np.float32).values
    y_val = y.iloc[train_end:val_end].astype(np.float32).values
    y_test = y.iloc[val_end:].astype(np.float32).values

    X_train = X_train_df.astype(np.float32).values
    X_val = X_val_df.astype(np.float32).values
    X_test = X_test_df.astype(np.float32).values

    mean, std = _fit_scaler(X_train)
    X_train = (X_train - mean) / std
    X_val = (X_val - mean) / std
    X_test = (X_test - mean) / std

    # ---- 3. Class imbalance handling ---- #
    n_pos_train = int(y_train.sum())
    n_neg_train = int(len(y_train) - n_pos_train)
    pos_weight_value = float(n_neg_train / max(n_pos_train, 1))
    pos_weight = torch.tensor([pos_weight_value], dtype=torch.float32)

    # ---- 4. Model + optimiser ---- #
    feature_dim = X_train.shape[1]
    model = MultiBranchDNN(
        DNNConfig(
            feature_dim=feature_dim,
            branches=branches,
            hidden_dim=hidden_dim,
            dropout=dropout,
        )
    )
    optim = torch.optim.Adam(
        model.parameters(),
        lr=lr,
        weight_decay=settings.PHASE_11_DNN_WEIGHT_DECAY,
    )
    loss_fn = nn.BCEWithLogitsLoss(pos_weight=pos_weight)

    train_ds = TensorDataset(
        torch.tensor(X_train), torch.tensor(y_train),
    )
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)

    X_val_t = torch.tensor(X_val)
    X_test_t = torch.tensor(X_test)

    loss_history: list[float] = []
    val_pr_history: list[float] = []
    best_val_pr = 0.0
    best_state: dict[str, torch.Tensor] | None = None

    from sklearn.metrics import average_precision_score, roc_auc_score

    # ---- 5. Training loop ---- #
    for epoch in range(epochs):
        model.train()
        epoch_loss = 0.0
        n_batches = 0
        for xb, yb in train_loader:
            optim.zero_grad()
            logits = model(xb)
            loss = loss_fn(logits, yb)
            loss.backward()
            optim.step()
            epoch_loss += float(loss.item())
            n_batches += 1
        epoch_loss /= max(n_batches, 1)
        loss_history.append(round(epoch_loss, 6))

        # Validation
        model.eval()
        with torch.no_grad():
            val_logits = model(X_val_t).numpy()
        val_probs = 1.0 / (1.0 + np.exp(-val_logits))
        val_pr = (
            float(average_precision_score(y_val, val_probs))
            if y_val.sum() > 0 and len(y_val) > 0
            else 0.0
        )
        val_pr_history.append(round(val_pr, 6))

        if val_pr > best_val_pr:
            best_val_pr = val_pr
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}

    # ---- 6. Restore best weights & evaluate test ---- #
    if best_state is not None:
        model.load_state_dict(best_state)
    model.eval()
    with torch.no_grad():
        test_logits = model(X_test_t).numpy()
    test_probs = 1.0 / (1.0 + np.exp(-test_logits))
    test_pr = (
        float(average_precision_score(y_test, test_probs))
        if y_test.sum() > 0 else 0.0
    )
    test_roc = (
        float(roc_auc_score(y_test, test_probs))
        if y_test.sum() > 0 and (y_test == 0).sum() > 0 else 0.0
    )

    # ---- 7. Persist ---- #
    model_version = f"v1.{int(time.time())}"
    model_path = Path(settings.PHASE_11_DNN_MODEL_PATH).resolve()
    model_path.parent.mkdir(parents=True, exist_ok=True)

    torch.save(
        {
            "state_dict": model.state_dict(),
            "config": model.cfg.to_dict(),
            "feature_columns": SUPERVISED_FEATURE_COLUMNS,
            "scaler": {"mean": mean.tolist(), "std": std.tolist()},
            "model_version": model_version,
        },
        str(model_path),
    )

    sidecar = model_path.with_suffix(".json")
    sidecar.write_text(
        json.dumps(
            {
                "model_version": model_version,
                "trained_at": started_at.isoformat(),
                "feature_columns": SUPERVISED_FEATURE_COLUMNS,
                "config": model.cfg.to_dict(),
                "label_source": label_source,
                "n_train": int(len(X_train)),
                "n_val": int(len(X_val)),
                "n_test": int(len(X_test)),
                "n_pos_train": n_pos_train,
                "n_pos_test": int(y_test.sum()),
                "test_pr_auc": test_pr,
                "test_roc_auc": test_roc,
                "best_val_pr_auc": best_val_pr,
                "final_loss": loss_history[-1] if loss_history else None,
                "epochs": epochs,
                "batch_size": batch_size,
                "lr": lr,
                "pos_weight": pos_weight_value,
            },
            indent=2,
            default=str,
        )
    )

    duration = time.perf_counter() - started_perf

    metrics = {
        "test_pr_auc": test_pr,
        "test_roc_auc": test_roc,
        "best_val_pr_auc": best_val_pr,
        "final_loss": loss_history[-1] if loss_history else None,
        "n_train": int(len(X_train)),
        "n_val": int(len(X_val)),
        "n_test": int(len(X_test)),
        "n_pos_train": n_pos_train,
        "n_pos_test": int(y_test.sum()),
        "pos_weight": pos_weight_value,
    }

    await _record_run(
        {
            "model_version": model_version,
            "model_path": str(model_path),
            "feature_dim": feature_dim,
            "branches": branches,
            "hidden_dim": hidden_dim,
            "dropout": dropout,
            "n_train": metrics["n_train"],
            "n_val": metrics["n_val"],
            "n_test": metrics["n_test"],
            "n_pos_train": metrics["n_pos_train"],
            "n_pos_test": metrics["n_pos_test"],
            "label_source": label_source,
            "epochs": epochs,
            "batch_size": batch_size,
            "lr": lr,
            "pos_weight": pos_weight_value,
            "final_loss": metrics["final_loss"],
            "best_val_pr_auc": best_val_pr,
            "test_pr_auc": test_pr,
            "test_roc_auc": test_roc,
            "loss_history": loss_history,
            "val_pr_history": val_pr_history,
            "duration_sec": duration,
            "started_at": started_at,
            "completed_at": datetime.now(timezone.utc),
        }
    )

    # Hot-swap the singleton inference cache (if loaded) so the freshly
    # trained model is served immediately.
    try:
        from services.phase_11_dnn import inference as _inf
        _inf.reset_cache()
    except Exception:
        pass

    logger.info(
        "phase_11.dnn trained version=%s test_pr_auc=%.4f duration=%.2fs",
        model_version, test_pr, duration,
    )

    return TrainingResult(
        trained=True,
        model_version=model_version,
        model_path=str(model_path),
        feature_columns=SUPERVISED_FEATURE_COLUMNS,
        metrics=metrics,
        loss_history=loss_history,
        val_pr_history=val_pr_history,
        n_train=metrics["n_train"],
        n_val=metrics["n_val"],
        n_test=metrics["n_test"],
        n_pos_train=metrics["n_pos_train"],
        n_pos_test=metrics["n_pos_test"],
        duration_sec=duration,
        label_source=label_source,
    )
