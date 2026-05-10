# Model Card — `fraud_dnn` v1 (Phase 11)

> **Status:** SHADOW MODEL.  Not served to end users.
> **Promotion gate:** Phase 5 `evaluate_shadow()` must return `passed=True`
> over a 7+ day window with `sample_n >= 1000` *and*
> `PHASE_11_DNN_PROMOTED` set to `true` by an admin.

## 1. Intended use

Detect fraudulent UPI / card debit transactions via a multi-branch
deep neural network operating on the **same 18-feature vector** used by
the existing Phase 3 XGBoost model.  The DNN exists to give SmartSpend a
clean migration path toward Stripe Radar's published 2022+ architecture
("Network-in-Neuron" — several parallel MLP branches whose outputs are
summed).

## 2. Architecture

* `MultiBranchDNN` (PyTorch, CPU): 4 independent MLP branches, hidden
  dim 128, dropout 0.15.  Each branch is a 3-layer MLP
  (`Linear → ReLU → Dropout` × 2 → `Linear`).  Branch logits are summed,
  then sigmoid-activated at inference.
* Features: identical canonical column order to XGBoost
  (`SUPERVISED_FEATURE_COLUMNS` from
  `ml_training/feature_engineering.py`).  No DNN-specific features —
  this is a deliberate choice so that train/serve skew is impossible.
* Scaler: per-feature mean/std fitted on the training split only,
  saved alongside the weights in the same `.pt` file.

## 3. Training data

| Source | Volume on this branch |
| --- | --- |
| `transactions.is_fraud = TRUE` | **0** as of 2026-05-09 |
| `transactions.anomaly_flag = TRUE` | 181 rows |
| Synthetic fraud injection (`generate_synthetic_fraud`) | ~1% rate over 5 000 synthetic rows when DB labels insufficient |

The trainer **prefers `is_fraud` first**, falls back to `anomaly_flag`
when `is_fraud` has < 5 positives, and finally to the same synthetic
generator the bootstrap script uses when neither is available.  The
chosen source is recorded in `dnn_training_runs.label_source` for every
run so the model card never lies about provenance.

## 4. Honest performance caveats

* **At the current label volume (0 real `is_fraud`, 181 anomaly proxy),
  any held-out PR-AUC > 0.85 is academic.**  The synthetic generator
  inserts patterns the model can trivially learn; held-out test set is
  drawn from the same distribution.  **Production claims are not
  supported by this checkpoint.**
* **A v2 model card will be eligible only after** a) `transactions.is_fraud`
  has ≥ 1 000 positives from real Phase 8 feedback, and b) Phase 5
  `evaluate_shadow()` shows non-regression for 7 consecutive days.

## 5. Storage and lifecycle

| Asset | Location |
| --- | --- |
| Weights + config + scaler | `models/fraud_dnn_v1.pt` (path configurable via `PHASE_11_DNN_MODEL_PATH`) |
| Sidecar JSON (metrics + provenance) | `models/fraud_dnn_v1.json` |
| Training-run log | Postgres `dnn_training_runs` |
| Shadow predictions | Postgres `shadow_predictions` (Phase 5 schema, reused) |

`reset_cache()` is invoked automatically after each successful training
run so the next request hot-swaps to the new weights without restart.

## 6. Feature flags

* `PHASE_11_DNN_ENABLED` — turn the DNN on as a SHADOW scorer.
* `PHASE_11_DNN_PROMOTED` — additional flag required to allow the DNN
  output to actually blend into the served risk score.  Default: `false`.
* `PHASE_11_DNN_BLEND_WEIGHT` — weight ∈ [0, 1] applied to the DNN
  probability when promoted.  Default `0.5`.  At promotion, start at
  `0.5` (true ensemble), then move toward `1.0` only after each
  10-percentage-point step holds for ≥ 7 days of `evaluate_shadow()`
  passing.

## 7. Rollback

Set `PHASE_11_DNN_ENABLED=false` (instant; no restart needed if the
hybrid scorer's `reload_models()` endpoint is called).  Or `git revert`
the Phase 11 commit, which removes both the routes and the
hybrid-scorer hook in a single change.

## 8. What would change this card

The card moves from "academic / shadow" to "production-eligible" when:

1. **Real labels:** `transactions.is_fraud = TRUE` count ≥ 1 000.
2. **Out-of-sample PR-AUC ≥ XGBoost baseline** on a held-out *real*
   week (not synthetic).
3. **Per-segment regression check** (`shadow_logger._check_segment_regression`)
   green for ≥ 7 days at promoted blend ≥ 0.5.

Until all three pass, the model is shadow-only and this card stays.
