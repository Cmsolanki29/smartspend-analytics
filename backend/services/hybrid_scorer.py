"""HybridScorer — weighted blend of unsupervised + supervised fraud detection.

Phase 3: Supervised Model Layer.
Phase 5 additions: shadow model scoring, canary routing, MLflow registry loading.
Phase 7 additions: SHAP TreeExplainer integration.
Phase 8 additions: counterfactual hold-out.
  When a transaction is ALLOWED with a borderline score (75–85 by default),
  1% of these transactions are inserted into the review_queue with priority='low'
  and action='allow'.  After 90 days without a dispute, they can be labeled as
  'legitimate' in a batch job, providing ground-truth negatives for XGBoost.

  Why borderline ALLOW?  These are the hardest cases for the model.  By tracking
  a sample through time, we build a high-quality negative label pool that reduces
  false positive rates in the next retrain cycle.
  - After supervised prediction, calls shap_explainer.explain(feature_vec).
  - Populates ScoreResult.explanation_detail with structured SHAP output.
  - Populates ScoreResult.explanation with flat top-3 driver text.
  - Calls shap_explainer.reload(model) after any model load/reload.

Dependencies: services/ml_model.py (EnsembleAnomalyDetector), xgboost,
              ml_training/feature_engineering.py, ml_training/train_supervised.py,
              services/ml_registry/registry.py (Phase 5),
              services/explainability/shap_explainer.py (Phase 7),
              core/config.py.
Performance budget: score() < 120ms (adds ~15ms for SHAP on 500-tree XGBoost);
                    score_with_shadow() < 130ms.

Architecture:
  ┌─────────────────────────────────────────────────────┐
  │                   HybridScorer                       │
  │                                                     │
  │  ┌────────────────────┐                             │
  │  │ EnsembleAnomalyDet │ ← Layer 1 (unsup)           │
  │  └────────────────────┘                             │
  │            +                                        │
  │  ┌────────────────────┐   ┌─────────────────────┐   │
  │  │  XGBoost (prod)    │   │ XGBoost (shadow)    │   │
  │  │  Layer 2           │   │ logged only, never  │   │
  │  └────────────────────┘   │ returned to user    │   │
  │                            └─────────────────────┘   │
  │  final = UNSUP_WEIGHT * unsup + SUP_WEIGHT * sup     │
  │         (0.30/0.70 when both available)              │
  └─────────────────────────────────────────────────────┘

Phase 5 canary routing:
  When a canary model exists, _should_use_canary(txn_id) routes
  CANARY_PERCENTAGE % of traffic deterministically (MD5 hash of txn_id).

Cold-start behaviour:
  - User has no trained unsup model → cold_start(), full weight on sup.
  - Supervised model file missing → 1.0 weight on unsup only.
  - Both missing → ScoreResult.cold_start() default.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from typing import Any, Optional

import numpy as np

from core.config import get_settings
from ml_training.feature_engineering import (
    SUPERVISED_FEATURE_COLUMNS,
    assembled_to_feature_vector,
)
from ml_training.train_supervised import load_model
from schemas.score import ScoreResult
from services.ml_model import EnsembleAnomalyDetector

logger = logging.getLogger(__name__)

# Version string: bumped when scoring logic changes (triggers shadow evaluation).
HYBRID_VERSION = "hybrid-unsup-xgb-v1.0"


class HybridScorer:
    """Fraud scorer combining unsupervised ensemble with supervised XGBoost.

    Responsibilities:
      - Owns a reference to the EnsembleAnomalyDetector (unsup layer).
      - Loads the production XGBoost model from MLflow registry (Phase 5) or disk.
      - Optionally loads a shadow model for dual-scoring (Phase 5).
      - Blends scores using configurable weights from Settings.
      - Exposes reload_models() for hot-reload after retraining (Phase 5).
      - Routes canary traffic deterministically via MD5 hash (Phase 5).

    Usage (async context):
        result: ScoreResult = await hybrid_scorer.score(user_id, txn_dict, assembled_feats)
        result, shadow_score = await hybrid_scorer.score_with_shadow(user_id, txn, feats)
    """

    def __init__(self, detector: EnsembleAnomalyDetector) -> None:
        """Initialise HybridScorer wrapping an existing EnsembleAnomalyDetector.

        Model loading order (Phase 5):
          1. Try MLflow registry Production stage.
          2. Fall back to SUPERVISED_MODEL_PATH on disk (Phase 3 behavior).
          3. If neither available → unsup-only mode.
        Also loads shadow (Staging) model from registry if available.
        Phase 7: after loading the production model, injects it into
        the module-level shap_explainer singleton.

        Args:
            detector: Singleton EnsembleAnomalyDetector (from services/ml_model.py).
        """
        self._detector = detector
        self._sup_model: Any | None = None        # production XGBoost
        self._shadow_model: Any | None = None     # shadow XGBoost (Phase 5)
        self._canary_model: Any | None = None     # canary XGBoost (Phase 5)
        self._sup_model_path: str = get_settings().SUPERVISED_MODEL_PATH
        self._load_all_models()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    async def score_with_shadow(
        self,
        user_id: int | str,
        txn: dict[str, Any],
        features: dict[str, Any] | None = None,
    ) -> tuple[ScoreResult, Optional[float]]:
        """Score with the production model AND compute a shadow score (if shadow model exists).

        The shadow score is returned to the caller for fire-and-forget logging
        (via shadow_logger.log()), but is NEVER returned to the end user.

        The prod model respects canary routing: if a canary model is deployed
        and `_should_use_canary(hash(txn))` returns True, the canary model is
        used as the "prod" model for that request.

        Args:
            user_id:  User identifier.
            txn:      Raw transaction dict.
            features: Pre-assembled feature dict.

        Returns:
            Tuple of (ScoreResult from prod/canary model, shadow_score float or None).
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._score_with_shadow_sync, int(user_id), txn, features
        )

    def _score_with_shadow_sync(
        self,
        user_id: int,
        txn: dict[str, Any],
        features: dict[str, Any] | None,
    ) -> tuple[ScoreResult, Optional[float]]:
        """Synchronous shadow scoring (runs in thread executor)."""
        # Canary routing: deterministically route % of traffic to canary model
        active_sup = self._sup_model
        if self._canary_model is not None:
            txn_key = str(txn.get("amount", "")) + str(txn.get("transaction_time", ""))
            if self._should_use_canary(txn_key):
                active_sup = self._canary_model

        prod_result = self._score_sync_with_model(user_id, txn, features, active_sup)

        # Shadow score (uses shadow model, not canary)
        shadow_score: Optional[float] = None
        if self._shadow_model is not None and features is not None:
            shadow_score = self._run_supervised_with_model(self._shadow_model, features)

        # ── Phase 11: DNN shadow scoring ────────────────────────────────
        # When PHASE_11_DNN_ENABLED=true and a trained .pt file exists,
        # the DNN's probability becomes the shadow score (overrides any
        # XGBoost shadow above) so Phase 5's evaluate_shadow() runs the
        # 24h regression check against the DNN.  The DNN result is NEVER
        # served to the end user unless PHASE_11_DNN_PROMOTED is also on,
        # which is handled in _score_sync below.
        try:
            if features is not None:
                from services.phase_11_dnn import inference as _dnn_inf
                if _dnn_inf.is_enabled():
                    dnn_prob = _dnn_inf.predict_proba(features)
                    if dnn_prob is not None:
                        shadow_score = float(dnn_prob) * 100.0
                        # Surface in signals so the UI can show it.
                        if isinstance(prod_result.signals, dict):
                            prod_result.signals["dnn_shadow_score"] = round(shadow_score, 2)
                            prod_result.signals["dnn_shadow_source"] = "phase_11"
        except Exception as exc:  # noqa: BLE001
            logger.debug("hybrid_scorer: DNN shadow scoring skipped: %s", exc)

        return prod_result, shadow_score

    async def score(
        self,
        user_id: int | str,
        txn: dict[str, Any],
        features: dict[str, Any] | None = None,
    ) -> ScoreResult:
        """Score a single transaction using the hybrid ensemble.

        Async wrapper so callers can `await hybrid_scorer.score(...)` without
        worrying about whether the inner ML calls block the event loop.
        The CPU-bound parts run in a thread executor.

        Phase 10: when ``PHASE_10_GNN_ENABLED`` is True, the user's GNN
        embedding is fetched (Redis-first, DB-fallback) BEFORE entering
        the executor and stashed on the txn dict so the sync scorer can
        surface it in ``signals``.  We deliberately don't blend it into
        the score yet — at the current data scale (4 users) the GNN
        embedding adds topology context but no validated accuracy lift,
        and shipping a blended weight without measurement would be a
        model-card lie.  Phase 11/12 will use the embedding as a real
        feature once labels and users grow.

        Returns:
            ScoreResult with both unsup_score and sup_score populated.
        """
        # ── Phase 10: best-effort GNN embedding fetch (additive, no blending)
        try:
            settings = get_settings()
            if getattr(settings, "PHASE_10_GNN_ENABLED", False) and user_id is not None:
                from services.phase_10_gnn.inference import get_user_embedding
                emb = await get_user_embedding(int(user_id))
                if emb:
                    txn = {**txn, "_gnn_embedding": emb}
        except Exception as exc:  # noqa: BLE001
            # Never block scoring on a GNN lookup failure.
            logger.debug("hybrid_scorer: GNN embedding fetch skipped: %s", exc)

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._score_sync, int(user_id), txn, features
        )

    def reload_models(self) -> None:
        """Hot-reload production, shadow, and canary models from MLflow registry.

        Phase 7: also reloads the SHAP explainer with the new production model.
        Called by retrain_scheduler after a promotion, and by the admin
        POST /api/admin/models/reload endpoint.  Thread-safe: assignments are atomic.
        """
        self._load_all_models()
        logger.info(
            "hybrid_scorer.reload_models: prod=%s shadow=%s canary=%s shap=%s",
            "loaded" if self._sup_model else "none",
            "loaded" if self._shadow_model else "none",
            "loaded" if self._canary_model else "none",
            "ready" if _get_shap_explainer().available else "unavailable",
        )

    def score_sync(
        self,
        user_id: int | str,
        txn: dict[str, Any],
        features: dict[str, Any] | None = None,
    ) -> ScoreResult:
        """Synchronous version of score() for non-async callers (tests, batch scripts)."""
        return self._score_sync(int(user_id), txn, features)

    def should_counterfactual_hold_out(self, score: int, action: str) -> bool:
        """Return True if this transaction should be sampled for counterfactual measurement.

        Sampling policy:
          - Action must be 'allow' (we only track let-through transactions).
          - Score must be in the borderline range [75, 85] (configurable via Settings).
          - 1% random sample using time-based pseudo-random selection.

        The 1% is intentionally NOT cryptographically random — we want
        reproducibility in tests and don't need security here.  The exact
        sample will drift over time, which is fine for training purposes.

        Args:
            score:  Final risk score (0–100).
            action: Decision action string.

        Returns:
            True if this transaction should be inserted into the counterfactual queue.
        """
        if action != "allow":
            return False
        lo = getattr(get_settings(), "COUNTERFACTUAL_SCORE_LO", 75)
        hi = getattr(get_settings(), "COUNTERFACTUAL_SCORE_HI", 85)
        if not (lo <= score <= hi):
            return False
        # 1% sampling: use current time modulo 100
        import time as _time
        return int(_time.time() * 1000) % 100 == 0

    def reload_supervised(self, model_path: str | None = None) -> bool:
        """Hot-reload the production supervised model from disk.

        Kept for backwards compatibility with the Phase 3 admin endpoint.
        Phase 5 callers should prefer reload_models() which also loads shadow/canary.

        Args:
            model_path: Override path; if None uses SUPERVISED_MODEL_PATH from config.

        Returns:
            True if model loaded successfully, False otherwise.
        """
        path = model_path or get_settings().SUPERVISED_MODEL_PATH
        new_model = load_model(path)
        if new_model is not None:
            self._sup_model = new_model
            self._sup_model_path = path
            logger.info("hybrid_scorer.reload_supervised: loaded from %s", path)
            return True
        logger.warning("hybrid_scorer.reload_supervised: no model at %s", path)
        return False

    @property
    def has_supervised_model(self) -> bool:
        """Return True if the supervised layer is active."""
        return self._sup_model is not None

    @property
    def has_shadow_model(self) -> bool:
        """Return True if a shadow model is loaded for dual-scoring."""
        return self._shadow_model is not None

    @property
    def detector_version(self) -> str:
        return HYBRID_VERSION if self._sup_model else self._detector.DETECTOR_VERSION

    # ------------------------------------------------------------------ #
    # Canary routing
    # ------------------------------------------------------------------ #

    def _should_use_canary(self, key: str) -> bool:
        """Deterministic canary routing: MD5(key) mod 100 < canary_percentage.

        Using MD5 of a transaction-specific key ensures:
          - Same transaction always routes to the same model (reproducible).
          - Traffic is evenly distributed across the canary percentage.
          - No state required.

        Args:
            key: A string derived from transaction attributes (not txn_id since
                 scoring happens before DB insert).
        """
        try:
            settings = get_settings()
            pct = getattr(settings, "CANARY_PERCENTAGE", 0)
            if pct <= 0:
                return False
            digest = hashlib.md5(key.encode()).hexdigest()
            bucket = int(digest[:8], 16) % 100
            return bucket < pct
        except Exception:
            return False

    # ------------------------------------------------------------------ #
    # Private scoring logic (runs synchronously, off event loop)
    # ------------------------------------------------------------------ #

    def _score_sync_with_model(
        self,
        user_id: int,
        txn: dict[str, Any],
        features: dict[str, Any] | None,
        sup_model: Any | None,
    ) -> ScoreResult:
        """Core scoring using an explicit sup_model (allows canary injection)."""
        # Temporarily swap model, score, restore
        orig = self._sup_model
        self._sup_model = sup_model
        try:
            return self._score_sync(user_id, txn, features)
        finally:
            self._sup_model = orig

    def _score_sync(
        self,
        user_id: int,
        txn: dict[str, Any],
        features: dict[str, Any] | None,
    ) -> ScoreResult:
        t0 = time.perf_counter()
        settings = get_settings()

        # ---- Layer 1: unsupervised ensemble ---- #
        try:
            unsup_result: ScoreResult = self._detector.score_single(
                user_id, txn, features
            )
        except Exception as exc:
            logger.exception("hybrid_scorer: unsup layer failed uid=%s: %s", user_id, exc)
            elapsed = (time.perf_counter() - t0) * 1000
            return ScoreResult.cold_start(detector_version=self.detector_version, latency_ms=elapsed)

        unsup_score = unsup_result.unsup_score  # 0.0–1.0

        # ---- Layer 2: supervised XGBoost ---- #
        sup_score: Optional[float] = None
        feat_vec: Optional[np.ndarray] = None   # Phase 7: capture for SHAP
        if self._sup_model is not None and features is not None:
            sup_score, feat_vec = self._run_supervised_returning_vec(features)

        # ---- Blend ---- #
        if sup_score is not None:
            unsup_w = settings.UNSUP_WEIGHT   # default 0.30
            sup_w = settings.SUP_WEIGHT        # default 0.70
            blended = unsup_w * unsup_score + sup_w * sup_score
        else:
            blended = unsup_score

        # ── Phase 11: DNN promoted-mode blending ────────────────────────
        # Only applies when *both* PHASE_11_DNN_ENABLED and
        # PHASE_11_DNN_PROMOTED are true.  In shadow mode the DNN does
        # not influence the served score at all.
        dnn_blend_used = False
        try:
            from services.phase_11_dnn import inference as _dnn_inf
            if _dnn_inf.is_promoted() and features is not None:
                dnn_prob = _dnn_inf.predict_proba(features)
                if dnn_prob is not None:
                    w = float(getattr(settings, "PHASE_11_DNN_BLEND_WEIGHT", 0.5))
                    w = min(max(w, 0.0), 1.0)
                    blended = (1.0 - w) * blended + w * float(dnn_prob)
                    dnn_blend_used = True
        except Exception as exc:  # noqa: BLE001
            logger.debug("hybrid_scorer: DNN promoted blend skipped: %s", exc)

        # Scale to 0-100
        final_risk_score = int(round(min(max(blended * 100, 0), 100)))
        risk_level = _risk_level(final_risk_score, settings)

        elapsed_ms = (time.perf_counter() - t0) * 1000

        # Merge signals: unsup signals + supervised signal
        signals: dict[str, Any] = dict(unsup_result.signals)
        if sup_score is not None:
            signals["sup_score_raw"] = round(sup_score, 4)
            signals["unsup_score_raw"] = round(unsup_score, 4)
            signals["blend"] = f"{int(settings.UNSUP_WEIGHT*100)}%unsup+{int(settings.SUP_WEIGHT*100)}%sup"
        if dnn_blend_used:
            w_pct = int(round(settings.PHASE_11_DNN_BLEND_WEIGHT * 100))
            signals["dnn_blend"] = f"promoted_{w_pct}%"

        # ── Phase 10: surface the GNN embedding as a signal (no blending).
        gnn_emb = txn.get("_gnn_embedding") if isinstance(txn, dict) else None
        if isinstance(gnn_emb, list) and gnn_emb:
            try:
                norm = float(np.linalg.norm(np.asarray(gnn_emb, dtype=float)))
            except Exception:
                norm = 0.0
            signals["gnn_emb_dim"] = len(gnn_emb)
            signals["gnn_emb_norm"] = round(norm, 4)
            signals["gnn_blend"] = "feature_only"

        # ---- Phase 7: SHAP explanation ---- #
        explanation_detail: Optional[dict[str, Any]] = None
        explanation: str = _build_explanation(unsup_result.explanation, sup_score, final_risk_score)

        if feat_vec is not None and sup_score is not None:
            try:
                explainer = _get_shap_explainer()
                if explainer.available:
                    shap_result = explainer.explain(
                        feat_vec, SUPERVISED_FEATURE_COLUMNS, top_k=5
                    )
                    if shap_result.get("available"):
                        explanation_detail = shap_result
                        # Build flat top-3 explanation string from SHAP drivers
                        drivers = shap_result.get("top_drivers", [])[:3]
                        if drivers:
                            explanation = " | ".join(
                                d["human_readable"] for d in drivers
                            )
            except Exception as exc:
                logger.debug("hybrid_scorer: SHAP explain failed (non-fatal): %s", exc)

        logger.info(
            "hybrid_scored uid=%s risk_score=%d risk_level=%s unsup=%.3f "
            "sup=%s shap=%s latency_ms=%.1f",
            user_id, final_risk_score, risk_level,
            unsup_score,
            f"{sup_score:.3f}" if sup_score is not None else "none",
            "yes" if explanation_detail else "no",
            elapsed_ms,
        )

        return ScoreResult(
            risk_score=final_risk_score,
            risk_level=risk_level,
            unsup_score=unsup_score,
            sup_score=sup_score,
            signals=signals,
            explanation=explanation,
            explanation_detail=explanation_detail,
            detector_version=self.detector_version,
            latency_ms=round(elapsed_ms, 2),
        )

    def _run_supervised(self, features: dict[str, Any]) -> Optional[float]:
        """Convert assembled features to XGBoost feature vector and predict (prod model)."""
        return self._run_supervised_with_model(self._sup_model, features)

    def _run_supervised_returning_vec(
        self, features: dict[str, Any]
    ) -> tuple[Optional[float], Optional[np.ndarray]]:
        """Like _run_supervised but also returns the feature vector for SHAP (Phase 7).

        Returns:
            Tuple (fraud_probability, feature_vector) or (None, None) on failure.
        """
        if self._sup_model is None:
            return None, None
        try:
            feat_vec = assembled_to_feature_vector(features)
            proba = float(self._sup_model.predict_proba(feat_vec.reshape(1, -1))[0, 1])
            return min(max(proba, 0.0), 1.0), feat_vec
        except Exception as exc:
            logger.exception("hybrid_scorer: supervised layer failed: %s", exc)
            return None, None

    def _run_supervised_with_model(
        self, model: Any, features: dict[str, Any]
    ) -> Optional[float]:
        """Convert assembled features to XGBoost feature vector and predict using `model`.

        Returns fraud probability [0.0, 1.0] or None on failure.
        Used by shadow scoring (which doesn't need the feature vector).
        """
        if model is None:
            return None
        try:
            feat_vec = assembled_to_feature_vector(features)
            proba = float(model.predict_proba(feat_vec.reshape(1, -1))[0, 1])
            return min(max(proba, 0.0), 1.0)
        except Exception as exc:
            logger.exception("hybrid_scorer: supervised layer failed: %s", exc)
            return None

    def _load_all_models(self) -> None:
        """Load production, shadow, and canary models.

        Loading order for production:
          1. MLflow registry Production stage (Phase 5).
          2. Disk fallback: SUPERVISED_MODEL_PATH (Phase 3).
        Shadow / canary: only from MLflow registry Staging stage.
        """
        # Production model
        self._sup_model = self._load_from_registry_or_disk()

        # Shadow model (Staging in MLflow)
        self._shadow_model = self._load_shadow_from_registry()

        # Canary model: same Staging slot as shadow for now;
        # traffic_percentage controls what fraction sees it.
        self._canary_model = None  # set by retrain_scheduler when canary is active

        # Phase 7: inject production model into SHAP explainer
        if self._sup_model is not None:
            try:
                _get_shap_explainer().reload(self._sup_model)
            except Exception as exc:
                logger.warning("hybrid_scorer: SHAP explainer init failed (non-fatal): %s", exc)

        if self._sup_model is None:
            logger.info("hybrid_scorer: no supervised model — unsup-only mode")
        else:
            logger.info(
                "hybrid_scorer: production model loaded (features=%d) shadow=%s shap=%s",
                len(SUPERVISED_FEATURE_COLUMNS),
                "yes" if self._shadow_model else "no",
                "ready" if _get_shap_explainer().available else "unavailable",
            )

    def _load_from_registry_or_disk(self) -> Optional[Any]:
        """Try MLflow Production, fall back to disk."""
        try:
            from services.ml_registry.registry import model_registry
            model = model_registry.load_production()
            if model is not None:
                logger.info("hybrid_scorer: production model from MLflow registry")
                return model
        except Exception as exc:
            logger.info("hybrid_scorer: registry load failed (%s) — trying disk", exc)
        # Disk fallback
        model = load_model(self._sup_model_path)
        if model is not None:
            logger.info("hybrid_scorer: production model from disk %s", self._sup_model_path)
        return model

    def _load_shadow_from_registry(self) -> Optional[Any]:
        """Load shadow (Staging) model from MLflow registry."""
        try:
            from services.ml_registry.registry import model_registry
            return model_registry.load_shadow()
        except Exception as exc:
            logger.debug("hybrid_scorer: shadow model load failed: %s", exc)
            return None

    def _load_supervised_model(self) -> None:
        """Deprecated: use _load_all_models() instead. Kept for test compatibility."""
        self._sup_model = load_model(self._sup_model_path)
        if self._sup_model is None:
            logger.info(
                "hybrid_scorer: no supervised model at %s — using unsup-only mode",
                self._sup_model_path,
            )
        else:
            logger.info(
                "hybrid_scorer: supervised model loaded from %s (features=%d)",
                self._sup_model_path, len(SUPERVISED_FEATURE_COLUMNS),
            )


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _risk_level(score: int, settings: Any) -> str:
    """Map a 0-100 risk score to a risk level label using configured thresholds."""
    if score >= settings.RISK_BLOCK_THRESHOLD:
        return "CRITICAL"
    if score >= settings.RISK_CHALLENGE_THRESHOLD:
        return "HIGH"
    if score >= settings.RISK_REVIEW_THRESHOLD:
        return "MEDIUM"
    return "LOW"


def _build_explanation(unsup_explanation: str, sup_score: Optional[float], final_score: int) -> str:
    """Build a rule-based explanation fallback used when SHAP is unavailable.

    Phase 7: when SHAP succeeds, _score_sync replaces this with SHAP driver text.
    """
    parts: list[str] = []
    if unsup_explanation:
        parts.append(unsup_explanation)
    if sup_score is not None:
        sup_pct = int(round(sup_score * 100))
        parts.append(f"XGBoost fraud probability: {sup_pct}%")
    if not parts:
        parts.append(f"Blended risk score: {final_score}/100")
    return " | ".join(parts)


def _get_shap_explainer():
    """Lazy accessor for the module-level SHAPExplainer singleton (Phase 7).

    Using a function instead of a top-level import avoids circular imports
    and defers shap/xgboost loading until first use.
    """
    from services.explainability.shap_explainer import shap_explainer  # noqa: PLC0415
    return shap_explainer


# ------------------------------------------------------------------ #
# Module-level singleton (replaces direct usage of ml_detector in routes)
# ------------------------------------------------------------------ #
# Import is deferred to avoid circular imports (ml_model imports nothing from here).
def _create_hybrid_scorer() -> HybridScorer:
    from services.ml_model import ml_detector  # noqa: PLC0415
    return HybridScorer(detector=ml_detector)


hybrid_scorer: HybridScorer = _create_hybrid_scorer()
