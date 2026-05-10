"""Centralised settings loaded from environment variables via pydantic-settings.

Phase 1: Real-time event-driven scoring.
All tunable parameters live here so nothing is hardcoded across the codebase.
When ENV=prod, missing required vars raise an error at startup rather than at
the first request — fail-fast is intentional.

Performance budget: this module is imported once at startup; no runtime cost.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import quote_plus

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env early so individual env vars are visible to pydantic-settings.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=_PROJECT_ROOT / ".env", override=False)


class Settings(BaseSettings):
    """Application settings.  Loaded once and cached via get_settings()."""

    model_config = SettingsConfigDict(
        env_file=str(_PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------ #
    # Environment
    # ------------------------------------------------------------------ #
    ENV: Literal["dev", "staging", "prod"] = "dev"

    # ------------------------------------------------------------------ #
    # Database — asyncpg (new Phase 1 path)
    # Falls back to constructing from individual vars if DATABASE_URL absent.
    # ------------------------------------------------------------------ #
    DATABASE_URL: str = Field(default="")
    DB_HOST: str = Field(default="127.0.0.1")
    DB_PORT: int = Field(default=5432)
    DB_NAME: str = Field(default="smartspend_db")
    DB_USER: str = Field(default="postgres")
    DB_PASSWORD: str = Field(default="")

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def _build_database_url(cls, v: str) -> str:
        """Construct asyncpg-compatible DSN from individual vars when DATABASE_URL is absent."""
        if v:
            return v
        host = os.getenv("DB_HOST", "127.0.0.1")
        port = os.getenv("DB_PORT", "5432")
        name = os.getenv("DB_NAME", "smartspend_db")
        user = os.getenv("DB_USER", "postgres")
        password = os.getenv("DB_PASSWORD", "").strip('"').strip("'")
        # URL-encode password so special chars like @ # % don't break the DSN
        return f"postgresql://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{name}"

    # ------------------------------------------------------------------ #
    # Redis
    # ------------------------------------------------------------------ #
    REDIS_URL: str = "redis://localhost:6379/0"

    # ------------------------------------------------------------------ #
    # MLflow
    # ------------------------------------------------------------------ #
    MLFLOW_TRACKING_URI: str = "sqlite:///mlflow.db"

    # ------------------------------------------------------------------ #
    # Risk thresholds
    # ------------------------------------------------------------------ #
    RISK_BLOCK_THRESHOLD: int = 85
    RISK_CHALLENGE_THRESHOLD: int = 65
    RISK_REVIEW_THRESHOLD: int = 40

    # ------------------------------------------------------------------ #
    # Ensemble weights (unsupervised / supervised blend)
    # ------------------------------------------------------------------ #
    UNSUP_WEIGHT: float = 0.30
    SUP_WEIGHT: float = 0.70

    # ------------------------------------------------------------------ #
    # Feature store
    # ------------------------------------------------------------------ #
    FEATURE_TTL_SEC: int = 86400        # 24 h online store TTL
    BASELINE_TTL_SEC: int = 3600 * 72  # 3-day user baseline cache
    MATERIALIZER_INTERVAL_MIN: int = 15

    # ------------------------------------------------------------------ #
    # Alerts
    # ------------------------------------------------------------------ #
    ALERT_COOLDOWN_SEC: int = 600       # 10 min between same alert
    ALERT_HOURLY_CAP: int = 5           # digest mode above this

    # ------------------------------------------------------------------ #
    # MLOps
    # ------------------------------------------------------------------ #
    RETRAIN_SCHEDULE_CRON: str = "0 2 * * 0"  # Sunday 02:00 UTC
    DRIFT_PSI_ALERT_THRESHOLD: float = 0.25
    CANARY_PERCENTAGE: int = 5

    # ------------------------------------------------------------------ #
    # Supervised model
    # ------------------------------------------------------------------ #
    SUPERVISED_MODEL_PATH: str = "models/supervised_v0.pkl"
    SUPERVISED_MIN_TRAIN_LABELS: int = 50   # need at least this many labeled rows

    # ------------------------------------------------------------------ #
    # Performance hard-limit
    # ------------------------------------------------------------------ #
    SCORING_TIMEOUT_MS: int = 500       # Return 503 if exceeded

    # ------------------------------------------------------------------ #
    # Phase 9 — LLM Investigation Agent (Groq Llama)
    # ------------------------------------------------------------------ #
    # Master switch: when False, agent is fully disabled (zero LLM calls,
    # zero cost, no DB writes).  Default OFF — opt-in via env var.
    PHASE_9_AGENT_ENABLED: bool = False
    # Daily USD spend cap.  When exceeded, agent returns "inconclusive"
    # (fail-closed) until the next UTC day.
    PHASE_9_DAILY_BUDGET_USD: float = 1.00
    # Default Groq model.  Llama 3.3 70B has reliable tool calling.
    PHASE_9_DEFAULT_MODEL: str = "llama-3.3-70b-versatile"
    # Same model for high-stakes (score >= 85), but with lower temperature.
    PHASE_9_HIGH_STAKES_MODEL: str = "llama-3.3-70b-versatile"
    # Auto-trigger threshold: investigations launched on score >= this value.
    PHASE_9_AUTO_TRIGGER_SCORE: int = 60
    # Per-investigation safety caps.
    PHASE_9_MAX_TOOL_ROUNDS: int = 8
    PHASE_9_MAX_OUTPUT_TOKENS: int = 1500
    PHASE_9_TIMEOUT_SEC: int = 30

    # ------------------------------------------------------------------ #
    # Phase 10 — Graph Neural Network (heterogeneous GraphSAGE)
    # ------------------------------------------------------------------ #
    # Master switch: when False, the GNN is fully bypassed and the hybrid
    # scorer continues to work exactly as before.
    PHASE_10_GNN_ENABLED: bool = False
    # Embedding dimension produced per user.  64 is a sane default — wide
    # enough to be useful, small enough to fit in Redis cheaply.
    PHASE_10_EMBED_DIM: int = 64
    # GraphSAGE depth.  2 layers covers user -> merchant -> user reach,
    # which is enough for fraud-ring detection at our scale.
    PHASE_10_NUM_LAYERS: int = 2
    # Default training look-back (days) — keeps the graph fresh.
    PHASE_10_TRAINING_DAYS: int = 90
    # Training hyperparams (kept conservative for laptop CPU).
    PHASE_10_EPOCHS: int = 60
    PHASE_10_LR: float = 1e-2
    # Redis TTL for cached embeddings (24 h) — refreshed on each retrain.
    PHASE_10_EMBED_TTL_SEC: int = 86400
    # Minimum users in the graph below which we *refuse* to train.  Below
    # this, the GNN is overfitting noise and we'd be lying with a model card.
    PHASE_10_MIN_USERS_FOR_TRAINING: int = 3
    # Honest cap on supervised contribution to total loss.  Most of our
    # signal is unsupervised contrastive when labels are sparse.
    #
    # NOTE (audit-2): this knob is *Phase 10 GNN only* — it controls the
    # supervised vs unsupervised mix in the GraphSAGE training loss
    #     L = (1 - w) * L_unsup_BPR  +  w * L_sup_BCE
    # in `backend/services/phase_10_gnn/trainer.py`.
    # It is **not** related to Phase 11 DNN.  The DNN has its own
    # `PHASE_11_*` settings further down in this file.  Do not rename
    # this to `PHASE_11_*` — it would break the GNN trainer and the
    # `.env` schema.  See CTO_AUDIT.md issue #2.
    PHASE_10_SUPERVISED_LOSS_WEIGHT: float = 0.3

    # ------------------------------------------------------------------ #
    # Phase 11 — Multi-branch DNN (Stripe Radar-style migration path)
    # ------------------------------------------------------------------ #
    # Master switch: when False, the DNN is a complete no-op.  Even when
    # True, the DNN is initially deployed as a SHADOW model — its score
    # is logged via the existing Phase 5 shadow_logger and NEVER served
    # to end users until 24h of regression-free data accumulates.
    PHASE_11_DNN_ENABLED: bool = False
    # The "promoted" flag flips the DNN from shadow to active production.
    # We default it to False so a freshly-trained DNN never silently
    # replaces XGBoost — promotion is a deliberate admin action.
    PHASE_11_DNN_PROMOTED: bool = False
    # Shadow-mode blending weight (used only when DNN is promoted).  At
    # promotion time it starts at 0.5 (true ensemble) and can be raised
    # to 1.0 once segment-regression checks remain green.
    PHASE_11_DNN_BLEND_WEIGHT: float = 0.5
    # Architecture
    PHASE_11_DNN_BRANCHES: int = 4
    PHASE_11_DNN_HIDDEN: int = 128
    PHASE_11_DNN_DROPOUT: float = 0.15
    # Training
    PHASE_11_DNN_EPOCHS: int = 40
    PHASE_11_DNN_BATCH_SIZE: int = 256
    PHASE_11_DNN_LR: float = 1e-3
    PHASE_11_DNN_WEIGHT_DECAY: float = 1e-5
    # Where the trained model lives (PyTorch state-dict + JSON sidecar).
    PHASE_11_DNN_MODEL_PATH: str = "models/fraud_dnn_v1.pt"
    # Refuse to train if positive count below this — DNNs overfit
    # fastest on tiny positive sets.
    PHASE_11_MIN_POSITIVES_FOR_TRAINING: int = 20
    # audit-4: clip standardised inputs to +/- N stddevs at inference
    # time.  An out-of-distribution row (e.g. an admin's hand-typed
    # "extreme high-risk" smoke test) otherwise produces a wild z-score
    # and the sigmoid saturates to 0 or 1.  Set to 0.0 to disable.
    # Production fintechs typically clamp at 5 sigma.
    PHASE_11_INPUT_CLIP_STD: float = 5.0

    # ------------------------------------------------------------------ #
    # Phase 12 — Multi-Model Orchestrator (LLM-as-Judge)
    # ------------------------------------------------------------------ #
    # Master switch.  When False the orchestrator is a transparent
    # passthrough (it still records the routed-tier label for analytics
    # but performs no escalation, no LLM judge, and never overrides the
    # baseline DecisionEngine action).
    PHASE_12_ORCHESTRATOR_ENABLED: bool = False
    # Sub-switches — each is independently rollable.
    PHASE_12_AUTO_INVESTIGATE: bool = True       # auto-trigger Phase 9 LLM agent
    PHASE_12_JUDGE_ENABLED: bool = True          # LLM-as-Judge cross-check
    # Score thresholds for tier routing.  Inclusive on the lower bound.
    PHASE_12_TIER0_MAX: int = 30                 # < 30  → Tier 0 (rules-only)
    PHASE_12_TIER1_MAX: int = 60                 # < 60  → Tier 1 (XGBoost)
    PHASE_12_TIER2_MAX: int = 75                 # < 75  → Tier 2 (+ GNN)
    PHASE_12_TIER3_MAX: int = 85                 # < 85  → Tier 3 (+ DNN)
    # When auto-investigate fires, this is the synchronous variant the
    # /decide endpoint uses (different from the async fire-and-forget
    # path in alert_consumer).  Default off — synchronous LLM in the
    # decision path is opt-in to keep p99 latency bounded.
    PHASE_12_SYNC_INVESTIGATION: bool = False
    # LLM-as-Judge configuration — reuses the Phase 9 budget guard.
    PHASE_12_JUDGE_MODEL: str = "llama-3.3-70b-versatile"
    PHASE_12_JUDGE_TEMPERATURE: float = 0.1
    PHASE_12_JUDGE_MAX_TOKENS: int = 800
    # When |dnn_shadow_score - prod_score| >= this delta, the orchestrator
    # treats the decision as "model disagreement" and routes to the judge
    # even when the absolute score wouldn't normally qualify.
    PHASE_12_DNN_DISAGREE_DELTA: float = 25.0
    # If the judge requests an override (downgrade allow→review or
    # upgrade allow→challenge), the orchestrator only honours it when
    # the judge confidence is at least this value.  Below it, the
    # judge's opinion is logged but ignored.
    PHASE_12_JUDGE_MIN_CONFIDENCE: float = 0.70


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached singleton Settings instance."""
    return Settings()
