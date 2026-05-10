# Phase 9-12 — 2025/2026 Fintech Parity Upgrade

> Branch: `feature/phase-9-to-12-2026-parity`
> Goal: Bring SmartSpend / EXIQO from a 2022-era ML stack to architectural
> parity with PhonePe, IBM Safer Payments, FIS+Anthropic, and NVIDIA Blueprint.

This log is updated **per milestone**, not per commit.  Each phase is
strictly feature-flagged: setting the relevant `PHASE_x_*_ENABLED` to
`false` in `.env` cleanly disables the new code paths.

---

## Phase 9 — LLM Investigation Agent (Agentic AI)

**Status:** ✅ Implemented (this milestone)
**Closes gap to:** IBM Safer Payments, FIS+Anthropic, CommBank, PhonePe.

### What it does
When a transaction is scored at `risk_score >= PHASE_9_AUTO_TRIGGER_SCORE`
(default 60) — or an admin clicks "Run Investigation" — an LLM agent
investigates using a six-tool toolbox and returns:

* a structured decision (`fraud_confirmed` / `legitimate` / `inconclusive`),
* a 2-3 sentence plain-English narrative (Hinglish allowed),
* `key_evidence` bullets,
* optional `suggested_rules` for the rules engine,
* full token / cost / latency telemetry.

Each investigation is persisted to `risk_investigations` with PII redacted
and the day's spend logged in `risk_llm_budget_log`.

### Provider — Groq (OpenAI-compatible)
| Setting | Value |
| --- | --- |
| SDK | `openai>=1.51` (already pinned) pointed at `https://api.groq.com/openai/v1` |
| API key | `GROQ_API_KEY` (already in `.env`) |
| Default model | `llama-3.3-70b-versatile` |
| High-stakes (score ≥ 85) | `llama-3.3-70b-versatile`, `temperature=0.1` |
| Fallback | `llama-3.1-70b-versatile` (auto-retry on `model_not_found`) |
| Tool calling | OpenAI-compatible function-calling format |
| Pricing | $0.59 / 1M input, $0.79 / 1M output |
| Realistic cost / investigation | $0.001 – $0.003 |
| Default daily cap | $1.00 (`PHASE_9_DAILY_BUDGET_USD`) |

### Files added
```
backend/database/migrations/009_phase9_investigations.sql
backend/services/risk_common/__init__.py
backend/services/risk_common/pii_redactor.py
backend/services/risk_common/budget_guard.py
backend/services/risk_common/groq_llm_client.py
backend/services/phase_9_agent/__init__.py
backend/services/phase_9_agent/agent.py
backend/services/phase_9_agent/investigation_service.py
backend/services/phase_9_agent/prompts/system_prompt.txt
backend/services/phase_9_agent/prompts/investigation_template.txt
backend/services/phase_9_agent/tools/__init__.py
backend/services/phase_9_agent/tools/base_tool.py
backend/services/phase_9_agent/tools/user_history_tool.py
backend/services/phase_9_agent/tools/merchant_lookup_tool.py
backend/services/phase_9_agent/tools/fraud_pattern_tool.py
backend/services/phase_9_agent/tools/geo_velocity_tool.py
backend/services/phase_9_agent/tools/blacklist_tool.py
backend/services/phase_9_agent/tools/shap_context_tool.py
backend/routes/investigations.py
backend/tests/test_phase9_agent.py
```

### Files modified (additive only)
```
backend/core/config.py            — Phase 9 settings block
backend/main.py                   — import + register investigations router
backend/workers/alert_consumer.py — auto-trigger on score >= threshold
backend/requirements.txt          — added groq, torch, networkx pins
```

### Database
* Migration `009_phase9_investigations.sql` applied — creates
  `risk_investigations` and `risk_llm_budget_log`.

### API surface (new)
| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `GET`  | `/api/risk/investigations/health` | open | feature-flag + LLM availability |
| `POST` | `/api/risk/investigations/{txn_id}/run` | `X-Admin-Token` | manual trigger |
| `GET`  | `/api/risk/investigations/{txn_id}` | `X-Admin-Token` | latest investigation row |
| `GET`  | `/api/risk/investigations/budget/today` | `X-Admin-Token` | today's spend rollup |

### Hard safety rules in code
1. **PII redaction** — every transaction, every tool output passes through
   `services.risk_common.pii_redactor.redact_dict` before being sent to Groq.
2. **Budget guard** — `BudgetGuard.check_and_reserve` runs before every LLM
   call.  Over-cap → `BudgetExceeded` → agent returns `inconclusive`.
3. **Confidence floor** — even if the model says `fraud_confirmed`, a
   confidence < 0.6 is forced to `inconclusive` for human review.
4. **Round cap** — max 8 tool-call rounds per investigation.
5. **Wall-clock timeout** — 30 s, after which the agent returns `inconclusive`.
6. **Fail-safe** — every error path persists an `inconclusive` row with
   `error` populated.  Investigations never raise out to callers.
7. **Feature flag** — `PHASE_9_AGENT_ENABLED=false` (default) makes the
   whole subsystem a no-op: no DB writes, no LLM calls, no cost.

### Tests
`backend/tests/test_phase9_agent.py` — runs without network.  Coverage:

* PII redactor: 6-pattern coverage + recursive dict.
* Budget guard: over-cap raises, under-cap allows, pricing math.
* `FraudPatternTool`: KYC-scam matches, benign transactions don't.
* `BlacklistTool`: static-layer hit when DB unavailable.
* Agent: disabled flag → inconclusive; missing API key → inconclusive;
  end-to-end with mocked Groq tool-call → final JSON; low-confidence →
  forced inconclusive.

### Configuration — new env vars
```dotenv
# Phase 9 — opt-in
PHASE_9_AGENT_ENABLED=false             # set to true to turn the agent on
PHASE_9_DAILY_BUDGET_USD=1.00           # daily LLM spend cap, fail-closed
PHASE_9_DEFAULT_MODEL=llama-3.3-70b-versatile
PHASE_9_HIGH_STAKES_MODEL=llama-3.3-70b-versatile
PHASE_9_AUTO_TRIGGER_SCORE=60           # auto-investigate score >= this
PHASE_9_MAX_TOOL_ROUNDS=8
PHASE_9_MAX_OUTPUT_TOKENS=1500
PHASE_9_TIMEOUT_SEC=30
GROQ_API_KEY=<your key>                 # already configured in .env
```

### Honest caveats
* Model accuracy is bounded by the prompt and tools — not by ML
  performance.  The agent doesn't "know" anything our XGBoost / SHAP
  layer didn't already surface; it explains and contextualises.
* Tool data quality is the bottleneck.  `MerchantLookupTool` reads from
  our own transactions table (no third-party reputation feed yet);
  `GeoVelocityTool` is heuristic (no lat/long, just location strings).
* Until we collect more labelled fraud, the LLM's hit-rate on the
  `fraud_confirmed` decision will be low — by design (confidence floor).

### Rollback plan
* Soft (instant): set `PHASE_9_AGENT_ENABLED=false` and reload.
* Hard: `git revert <phase-9 commit>` — schema migration is forward-only
  but the tables are append-only; leaving them in place is safe.

---

## Phase 10 — Graph Neural Network (heterogeneous GraphSAGE)

**Status:** ✅ Implemented (this milestone).
**Closes gap to:** NVIDIA Blueprint pattern, PayPal, TigerGraph.

### What it does
Builds a heterogeneous graph from the transactions table
(user / merchant / category / location / bank — plus optional
device / ip / card when populated), trains a 2-layer GraphSAGE on
contrastive user↔merchant edges + a small supervised head, and
persists the resulting 64-dim user embedding to **both Redis (TTL) and
Postgres (durable)** so the hybrid scorer can fetch it cheaply at
score time.

### Architecture choice — pure PyTorch, no `torch_geometric`
PyG's wheels are fragile on Windows / Python 3.13 and would have broken
the branch's checkout-and-run guarantee.  We re-implement the SAGE-mean
aggregator using `scipy.sparse.csr_matrix` left-multiplied against node
embeddings.  The math is identical; only the package boundary differs.
Switching to PyG later is a 50-line change once a stable wheel exists.

### Files added
```
backend/database/migrations/010_phase10_gnn.sql
backend/services/phase_10_gnn/__init__.py
backend/services/phase_10_gnn/graph_builder.py
backend/services/phase_10_gnn/gnn_model.py
backend/services/phase_10_gnn/trainer.py
backend/services/phase_10_gnn/inference.py
backend/routes/gnn.py
backend/tests/test_phase10_gnn.py
backend/models/cards/fraud_gnn_v1.md
```

### Files modified (additive only)
```
backend/core/config.py           — Phase 10 settings block
backend/main.py                  — register gnn router
backend/services/hybrid_scorer.py — async pre-fetch + signals.gnn_emb_*
.env                              — Phase 10 env vars
```

### Database
* Migration `010_phase10_gnn.sql` applied — creates
  `gnn_user_embeddings` and `gnn_training_runs`.

### API surface (new)
| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `GET`  | `/api/risk/gnn/health` | open | feature flag + config |
| `POST` | `/api/risk/gnn/train?days=&epochs=&lr=` | `X-Admin-Token` | full pipeline |
| `GET`  | `/api/risk/gnn/status` | `X-Admin-Token` | last run + inventory |
| `GET`  | `/api/risk/gnn/users/{id}/embedding` | `X-Admin-Token` | one user's vector |

### Hybrid-scorer integration (intentionally conservative)
`HybridScorer.score()` pre-fetches the user's embedding asynchronously
when `PHASE_10_GNN_ENABLED=true` and surfaces it in `signals` as
`gnn_emb_dim`, `gnn_emb_norm`, `gnn_blend="feature_only"`.  We
**deliberately do not blend it into the score** — see model card for the
honest reasoning.  Phase 11/12 will use the embedding as a feature once
the data justifies a measured weight.

### Tests
`backend/tests/test_phase10_gnn.py` — **10 / 10 passing**, no network:

* Sparse utilities (empty matrix, row-normalisation, conv shape, full
  forward, supervised head).
* Graph builder (empty rows handled, anomaly-rate labelling correct).
* Trainer (skips with `insufficient_graph_data` reason on tiny graphs).
* Inference (Redis-hit, DB fallback, true-None when missing).

### Configuration — new env vars
```dotenv
PHASE_10_GNN_ENABLED=false
PHASE_10_EMBED_DIM=64
PHASE_10_NUM_LAYERS=2
PHASE_10_TRAINING_DAYS=90
PHASE_10_EPOCHS=60
PHASE_10_LR=0.01
PHASE_10_EMBED_TTL_SEC=86400
PHASE_10_MIN_USERS_FOR_TRAINING=3
PHASE_10_SUPERVISED_LOSS_WEIGHT=0.3
```

### Honest caveats (and why this is still the right ship)
* **Only 4 users in DB right now.**  Cannot learn fraud rings — there
  are no rings.  The architecture is production-grade; the *learned
  signal* is bounded by data scale.
* **No real `is_fraud` labels.**  Supervised loss uses
  `anomaly_flag` as a proxy.
* **Bipartite-ish graph** — `device_id`/`ip_address`/`card_token` are
  NULL on every row.  Phase 11/12 don't depend on these being populated;
  they will benefit dramatically when they are.
* See `backend/models/cards/fraud_gnn_v1.md` for the full caveat list.

### Rollback
* Soft (instant): set `PHASE_10_GNN_ENABLED=false` and reload.
* Hard: `git revert <phase-10 commit>` — both new tables are append-only
  and PII-free, so leaving them in place is safe.

## Phase 11 — DNN Migration Path

**Status:** ✅ Implemented (this milestone)
**Closes gap to:** Stripe Radar (DNN-only since 2022).

### What it does
Trains a **multi-branch DNN** (Stripe's "Network-in-Neuron" pattern — 4
parallel MLP branches whose logits are summed) on the *exact same*
18-feature vector that XGBoost uses today.  By default the DNN is a
SHADOW model:

1. `PHASE_11_DNN_ENABLED=true` → the DNN's score is computed in parallel
   with XGBoost and logged through the existing Phase 5 `shadow_logger`,
   so `evaluate_shadow()` runs the segment-regression + PSI checks
   directly against the DNN.  It does **not** influence the served risk
   score in this mode.
2. `PHASE_11_DNN_PROMOTED=true` *additionally* allows the DNN
   probability to blend into the production score with weight
   `PHASE_11_DNN_BLEND_WEIGHT` (default 0.5 — true ensemble).

This two-flag promotion gate is deliberate: a freshly trained DNN can
never silently replace XGBoost.  Rollback is one env-var flip away.

### Architecture
| Component | Choice | Why |
| --- | --- | --- |
| Framework | Pure PyTorch (CPU) | No `torch_geometric` / no GPU — checkout-and-run. |
| Branches | 4 × `Linear(d→128) → ReLU → Drop → Linear(128→64) → ReLU → Drop → Linear(64→1)` | ResNeXt / Stripe pattern; gives GBDT-like ensemble behaviour while staying differentiable. |
| Loss | `BCEWithLogitsLoss` with class-balanced `pos_weight` | Numerically stable; auto-handles imbalance. |
| Optimiser | Adam, `lr=1e-3`, `weight_decay=1e-5` | Standard tabular DNN choice. |
| Split | Time-based 70 / 15 / 15 | Prevents future-leak. |
| Scaler | Per-feature mean/std fitted on **train only**, saved inside the `.pt` file | Removes train/serve skew at inference time. |
| Storage | `models/fraud_dnn_v1.pt` + sidecar `.json` | Source of truth; no MLflow dependency required. |

### Label sourcing — honest waterfall
The trainer prefers labels in this order and records the choice in
`dnn_training_runs.label_source`:

1. `transactions.is_fraud = TRUE` if ≥ 5 positives.
2. `transactions.anomaly_flag = TRUE` if ≥ 5 positives.
3. Synthetic fraud (same `generate_synthetic_fraud` the bootstrap uses).

Empirical result on this branch: **0 real `is_fraud`, 181 anomaly_flag,
~5 000 synthetic** is what the `.pt` is trained on right now.  See
`backend/models/cards/fraud_dnn_v1.md` for the full honesty section.

### Files added
```
backend/database/migrations/011_phase11_dnn.sql
backend/services/phase_11_dnn/__init__.py
backend/services/phase_11_dnn/dnn_model.py
backend/services/phase_11_dnn/trainer.py
backend/services/phase_11_dnn/inference.py
backend/routes/dnn.py
backend/models/cards/fraud_dnn_v1.md
backend/tests/test_phase11_dnn.py
```

### Files modified
```
backend/core/config.py            (Phase 11 settings block)
backend/main.py                   (register /api/risk/dnn router)
backend/services/hybrid_scorer.py (DNN shadow + promoted-blend hooks)
.env                              (Phase 11 flags)
PHASE_9_TO_12_LOG.md              (this entry)
```

### API surface — `/api/risk/dnn/*`
| Method | Path | Purpose | Auth |
| --- | --- | --- | --- |
| GET  | `/health`             | Feature flag, model_loaded | open |
| POST | `/train`              | Train + persist a fresh DNN | `X-Admin-Token` |
| GET  | `/status`             | Cached snapshot + last `dnn_training_runs` row | admin |
| GET  | `/runs`               | Recent training runs (paged) | admin |
| POST | `/reload`             | Drop in-process model cache | admin |
| GET  | `/shadow/evaluation`  | Phase 5 segment-regression + PSI on shadow_predictions | admin |
| POST | `/predict`            | Sandbox a feature dict | admin |

### Honest caveats
* **At the current label volume** (0 real fraud, 181 anomaly proxy) any
  test PR-AUC ≥ 0.85 is academic: the synthetic generator inserts
  patterns the model can trivially learn.  This is documented in the
  model card and surfaced via `label_source` on every training run.
* **DNNs do not beat XGBoost on tabular data at this scale.**  The
  *architecture* is the deliverable; production accuracy claims have to
  wait on real labels (Phase 8 flywheel) and a clean `evaluate_shadow()`
  pass.

### Rollback
* Soft: `PHASE_11_DNN_ENABLED=false` (instant; hot-reload picks it up).
* Hard: `git revert <phase-11 commit>`.  `dnn_training_runs` is
  append-only and PII-free.

## Phase 12 — Multi-Model Orchestrator (LLM-as-Judge)
**Status:** queued.
Single decision-maker that routes between rules / hybrid / GNN / DNN /
LLM agent paths and uses an LLM as a judge for borderline cases.
