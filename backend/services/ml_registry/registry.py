"""MLflow-backed model registry for SmartSpend fraud detection models.

Phase 5: MLOps.
Dependencies: mlflow, asyncpg (for model_deployments table), core/config.py.
Performance budget: register_model < 5s; load_production < 2s (model is cached after first load).

Why a wrapper instead of using MLflow directly?
  1. Graceful degradation — if the MLflow server is unreachable, the system
     falls back to loading from disk (the Phase 3 behavior).
  2. Custom stage semantics — MLflow has None/Staging/Production/Archived.
     SmartSpend adds 'shadow' and 'canary' with traffic_percentage metadata,
     stored in the model_deployments table.
  3. Audit trail — promoted_by and metrics are persisted in Postgres alongside
     MLflow's own tracking, giving analysts a single source of truth.

Stage mapping (SmartSpend → MLflow):
  shadow     → Staging
  canary     → Staging (with traffic_percentage in model_deployments)
  production → Production
  archived   → Archived
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from core.config import get_settings
from ml_training.train_supervised import load_model as _load_model_from_disk

logger = logging.getLogger(__name__)

# Canonical model name used throughout the system
FRAUD_MODEL_NAME = "smartspend_fraud_xgb"

# MLflow stage constants (the registry understands both our names and MLflow's)
_STAGE_MAP: dict[str, str] = {
    "shadow":     "Staging",
    "canary":     "Staging",
    "production": "Production",
    "archived":   "Archived",
}
_REVERSE_STAGE_MAP: dict[str, str] = {
    "Staging":    "shadow",
    "Production": "production",
    "Archived":   "archived",
    "None":       "archived",
}


class ModelRegistry:
    """Wraps MLflow tracking + model registry with production-safe abstractions.

    All public methods are synchronous (blocking) since they are called from
    background workers and admin endpoints, never from the hot scoring path.
    The hot path loads models at startup and caches them in memory.

    Graceful degradation: every method logs a warning and returns None/False
    when MLflow is unavailable rather than propagating exceptions.
    """

    def __init__(self) -> None:
        """Configure MLflow tracking URI from settings.  Defers actual connection."""
        self._available = False
        self._client: Any | None = None
        import os

        if os.getenv("SMARTSPEND_SKIP_MLFLOW_INIT", "1").lower() not in ("1", "true", "yes"):
            self._init_mlflow()

    def _ensure_mlflow(self) -> None:
        if not self._available and self._client is None:
            self._init_mlflow()

    def _init_mlflow(self) -> None:
        """Attempt MLflow initialization.  Safe to call multiple times."""
        try:
            import mlflow
            import mlflow.xgboost
            settings = get_settings()
            mlflow.set_tracking_uri(settings.MLFLOW_TRACKING_URI)
            from mlflow.tracking import MlflowClient
            self._client = MlflowClient()
            # Ping the server with a lightweight call
            self._client.search_experiments(max_results=1)
            self._available = True
            logger.info("model_registry.init tracking_uri=%s", settings.MLFLOW_TRACKING_URI)
        except Exception as exc:
            logger.warning("model_registry.init_failed — MLflow unavailable: %s", exc)
            self._available = False

    # ------------------------------------------------------------------ #
    # Write operations (called by training pipeline)
    # ------------------------------------------------------------------ #

    def register_model(
        self,
        model: Any,
        name: str = FRAUD_MODEL_NAME,
        metrics: dict[str, Any] | None = None,
        hyperparams: dict[str, Any] | None = None,
    ) -> Optional[str]:
        """Log a trained XGBoost model to MLflow and register it.

        Args:
            model:       Trained XGBClassifier.
            name:        Registered model name (default FRAUD_MODEL_NAME).
            metrics:     Evaluation metrics dict (logged to MLflow run).
            hyperparams: Training hyperparameters (logged to MLflow run).

        Returns:
            Version string (e.g. "1", "2", ...) or None if MLflow unavailable.
        """
        if not self._available:
            logger.warning("register_model: MLflow unavailable — skipping registration")
            return None

        try:
            import mlflow
            import mlflow.xgboost

            with mlflow.start_run() as run:
                if hyperparams:
                    safe_params = {k: str(v) for k, v in hyperparams.items()}
                    mlflow.log_params(safe_params)
                if metrics:
                    numeric_metrics = {
                        k: float(v) for k, v in metrics.items()
                        if isinstance(v, (int, float)) and v is not None
                    }
                    if numeric_metrics:
                        mlflow.log_metrics(numeric_metrics)

                mlflow.xgboost.log_model(
                    model,
                    artifact_path="model",
                    registered_model_name=name,
                )
                run_id = run.info.run_id

            # Get the latest version just registered (always return str)
            versions = self._client.search_model_versions(f"name='{name}'")
            if versions:
                versions_sorted = sorted(versions, key=lambda v: int(v.version), reverse=True)
                version = str(versions_sorted[0].version)
            else:
                version = "1"

            logger.info(
                "model_registry.registered name=%s version=%s run_id=%s",
                name, version, run_id,
            )
            return version

        except Exception as exc:
            logger.exception("model_registry.register_failed: %s", exc)
            return None

    def promote(
        self,
        name: str,
        version: str,
        stage: str,
        promoted_by: str | None = None,
        metrics: dict | None = None,
        traffic_percentage: int = 0,
    ) -> bool:
        """Transition a model version to a new stage.

        Syncs both MLflow stage and the model_deployments Postgres table.

        Args:
            name:               Model name.
            version:            Version string.
            stage:              SmartSpend stage: 'shadow', 'canary', 'production', 'archived'.
            promoted_by:        Admin user identifier for audit.
            metrics:            Evaluation metrics to store in model_deployments.
            traffic_percentage: Canary traffic fraction (0-100).

        Returns:
            True if successful.
        """
        if not self._available:
            logger.warning("promote: MLflow unavailable — cannot promote %s v%s", name, version)
            return False

        mlflow_stage = _STAGE_MAP.get(stage, "Staging")

        try:
            self._client.transition_model_version_stage(
                name=name, version=version, stage=mlflow_stage
            )
            logger.info(
                "model_registry.promoted name=%s version=%s stage=%s mlflow_stage=%s",
                name, version, stage, mlflow_stage,
            )
            # Update Postgres model_deployments table asynchronously (best-effort)
            self._upsert_deployment_sync(
                name, version, stage, promoted_by, metrics or {}, traffic_percentage
            )
            return True
        except Exception as exc:
            logger.exception("model_registry.promote_failed name=%s v=%s: %s", name, version, exc)
            return False

    def _upsert_deployment_sync(
        self,
        model_name: str,
        version: str,
        stage: str,
        promoted_by: Optional[str],
        metrics: dict,
        traffic_percentage: int,
    ) -> None:
        """Synchronous psycopg2 write to model_deployments (called from background)."""
        try:
            import os
            import psycopg2
            from core.config import get_settings
            settings = get_settings()
            dsn = settings.DATABASE_URL
            conn = psycopg2.connect(dsn)
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO model_deployments
                    (model_name, version, stage, traffic_percentage, promoted_by, metrics)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (model_name, version, stage) DO UPDATE
                    SET traffic_percentage = EXCLUDED.traffic_percentage,
                        promoted_by        = EXCLUDED.promoted_by,
                        metrics            = EXCLUDED.metrics,
                        promoted_at        = NOW()
                """,
                (model_name, version, stage, traffic_percentage,
                 promoted_by, json.dumps(metrics)),
            )
            conn.commit()
            cur.close()
            conn.close()
        except Exception as exc:
            logger.warning("model_registry._upsert_deployment_sync failed: %s", exc)

    # ------------------------------------------------------------------ #
    # Read operations (called at startup + admin)
    # ------------------------------------------------------------------ #

    def load_production(self, name: str = FRAUD_MODEL_NAME) -> Optional[Any]:
        """Load the current Production-stage model from MLflow.

        Falls back to loading from SUPERVISED_MODEL_PATH on disk if MLflow
        is unavailable or no Production model exists.

        Returns:
            Trained XGBClassifier or None.
        """
        self._ensure_mlflow()
        if self._available:
            try:
                import mlflow.xgboost
                model_uri = f"models:/{name}/Production"
                model = mlflow.xgboost.load_model(model_uri)
                logger.info("model_registry.loaded_production name=%s", name)
                return model
            except Exception as exc:
                logger.info(
                    "model_registry.load_production_miss name=%s (%s) — fallback to disk",
                    name, exc,
                )

        # Disk fallback (Phase 3 behavior)
        settings = get_settings()
        return _load_model_from_disk(settings.SUPERVISED_MODEL_PATH)

    def load_shadow(self, name: str = FRAUD_MODEL_NAME) -> Optional[Any]:
        """Load the current Staging-stage model from MLflow as shadow model.

        Returns:
            Trained XGBClassifier or None.
        """
        self._ensure_mlflow()
        if not self._available:
            return None
        try:
            import mlflow.xgboost
            versions = self._client.get_latest_versions(name, stages=["Staging"])
            if not versions:
                return None
            model_uri = f"models:/{name}/Staging"
            model = mlflow.xgboost.load_model(model_uri)
            logger.info("model_registry.loaded_shadow name=%s", name)
            return model
        except Exception as exc:
            logger.info("model_registry.load_shadow_miss name=%s: %s", name, exc)
            return None

    def current_versions(self, name: str = FRAUD_MODEL_NAME) -> dict[str, Optional[str]]:
        """Return the current version string for each active stage.

        Returns:
            Dict with keys 'production', 'shadow', 'canary' — values are version
            strings or None if that stage has no model deployed.
        """
        if not self._available:
            return {"production": None, "shadow": None, "canary": None}
        try:
            result: dict[str, Optional[str]] = {
                "production": None, "shadow": None, "canary": None
            }
            for mlflow_stage, our_stage in [("Production", "production"), ("Staging", "shadow")]:
                versions = self._client.get_latest_versions(name, stages=[mlflow_stage])
                if versions:
                    result[our_stage] = versions[-1].version
            return result
        except Exception as exc:
            logger.warning("model_registry.current_versions failed: %s", exc)
            return {"production": None, "shadow": None, "canary": None}

    def list_all_versions(self, name: str = FRAUD_MODEL_NAME) -> list[dict]:
        """List all registered versions with their MLflow stage + metadata.

        Returns:
            List of dicts with version, stage, creation_timestamp, run_id.
        """
        if not self._available:
            return []
        try:
            versions = self._client.search_model_versions(f"name='{name}'")
            return [
                {
                    "version": v.version,
                    "mlflow_stage": v.current_stage,
                    "stage": _REVERSE_STAGE_MAP.get(v.current_stage, v.current_stage),
                    "run_id": v.run_id,
                    "created_at": str(v.creation_timestamp),
                }
                for v in versions
            ]
        except Exception as exc:
            logger.warning("model_registry.list_all_versions failed: %s", exc)
            return []

    def rollback(self, name: str = FRAUD_MODEL_NAME) -> bool:
        """Emergency rollback: archive current Production, promote previous to Production.

        Returns:
            True if rollback succeeded.
        """
        if not self._available:
            return False
        try:
            versions = self._client.search_model_versions(f"name='{name}'")
            prod_versions = [v for v in versions if v.current_stage == "Production"]
            if not prod_versions:
                logger.warning("rollback: no Production version to rollback")
                return False

            current = sorted(prod_versions, key=lambda v: int(v.version))[-1]
            self._client.transition_model_version_stage(
                name=name, version=current.version, stage="Archived"
            )

            # Find most recent previous Staging version
            staging_versions = [v for v in versions if v.current_stage == "Staging"]
            if staging_versions:
                prev = sorted(staging_versions, key=lambda v: int(v.version))[-1]
                self._client.transition_model_version_stage(
                    name=name, version=prev.version, stage="Production"
                )
                logger.info(
                    "rollback: archived v%s, promoted v%s to Production",
                    current.version, prev.version,
                )
            else:
                logger.warning("rollback: no staging version to promote after archiving v%s", current.version)

            return True
        except Exception as exc:
            logger.exception("rollback failed: %s", exc)
            return False


# Module-level singleton
model_registry = ModelRegistry()
