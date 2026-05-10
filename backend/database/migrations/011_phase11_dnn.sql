-- Phase 11: Multi-branch DNN (Stripe Radar-style)
--
-- Shadow predictions already live in `shadow_predictions` (created by
-- Phase 5).  We reuse it: the DNN becomes the producer of `shadow_score`
-- whenever PHASE_11_DNN_ENABLED is true, and the existing
-- ShadowLogger.evaluate_shadow() runs the 24h regression check.
--
-- This migration only adds a small training-run history table so the
-- /api/risk/dnn/status endpoint can render the loss curve and let the
-- model card cite reproducible numbers.

CREATE TABLE IF NOT EXISTS dnn_training_runs (
    id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    model_version   VARCHAR(40)  NOT NULL,
    model_path      TEXT         NOT NULL,

    -- Architecture
    feature_dim     INTEGER      NOT NULL,
    branches        INTEGER      NOT NULL,
    hidden_dim      INTEGER      NOT NULL,
    dropout         REAL         NOT NULL,

    -- Training data shape
    n_train         INTEGER      NOT NULL DEFAULT 0,
    n_val           INTEGER      NOT NULL DEFAULT 0,
    n_test          INTEGER      NOT NULL DEFAULT 0,
    n_pos_train     INTEGER      NOT NULL DEFAULT 0,
    n_pos_test      INTEGER      NOT NULL DEFAULT 0,
    label_source    VARCHAR(40)  NOT NULL DEFAULT 'synthetic_fraud',

    -- Hyperparameters
    epochs          INTEGER      NOT NULL,
    batch_size      INTEGER      NOT NULL,
    lr              REAL         NOT NULL,
    pos_weight      REAL         NOT NULL DEFAULT 1.0,

    -- Outcome
    final_loss      REAL         NULL,
    best_val_pr_auc REAL         NULL,
    test_pr_auc     REAL         NULL,
    test_roc_auc    REAL         NULL,
    loss_history    JSONB        NOT NULL DEFAULT '[]'::jsonb,
    val_pr_history  JSONB        NOT NULL DEFAULT '[]'::jsonb,
    duration_sec    REAL         NOT NULL DEFAULT 0,
    error           TEXT         NULL,

    started_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ  NULL
);

CREATE INDEX IF NOT EXISTS idx_dnn_runs_started
    ON dnn_training_runs (started_at DESC);

COMMENT ON TABLE dnn_training_runs IS
    'Phase 11: history of multi-branch DNN training runs with hyperparams + held-out metrics.';
