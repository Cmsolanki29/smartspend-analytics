/**
 * riskApi.js — Phase 1-8 Risk Engine API calls
 *
 * Auth pattern mirrors services/api.js:
 *   - JWT Bearer token from localStorage key "smartspend_access_token"
 *   - Admin endpoints additionally require X-Admin-Token header
 *
 * All functions return the response .data directly.
 * On error they throw — callers must catch and show RiskStatePlaceholder.
 */

import axios from "axios";
import { getAccessToken } from "./api";
import { getApiBaseUrl } from "./apiBaseUrl";

const ADMIN_TOKEN = process.env.REACT_APP_ADMIN_TOKEN || "dev-admin-secret";
const BASE = getApiBaseUrl();

// ── Axios client for regular JWT-authenticated risk calls ──────────────────
const riskClient = axios.create({ baseURL: BASE, timeout: 8000 });

riskClient.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ── Axios client for admin calls (JWT + X-Admin-Token) ────────────────────
const adminClient = axios.create({ baseURL: BASE, timeout: 8000 });

adminClient.interceptors.request.use((config) => {
  const token = getAccessToken();
  config.headers = config.headers || {};
  if (token) config.headers.Authorization = `Bearer ${token}`;
  config.headers["X-Admin-Token"] = ADMIN_TOKEN;
  return config;
});

// ── Helper ────────────────────────────────────────────────────────────────
const d = (res) => res.data;

// ── Phase 1 — Real-time event health ──────────────────────────────────────
// Backend health endpoint lives at GET /health (no /api prefix).
// Backend health lives at GET /health (no /api prefix). Strip trailing /api from API base.
const _BACKEND_ROOT = BASE.replace(/\/api\/?$/, "");
export const riskHealth = () =>
  axios.get(`${_BACKEND_ROOT}/health`, { timeout: 5000 })
    .then(d)
    .catch(() => ({ status: "degraded" }));

// ── Phase 2 — Feature store / behavior profile ────────────────────────────
// Not yet exposed on backend; graceful 404 → empty state
export const getBehaviorProfile = (userId, scope = null) => {
  const params = scope ? { scope, mode: scope } : {};
  return riskClient.get(`/risk/users/${userId}/behavior-profile`, { params }).then(d);
};

// ── Phase 3 — Fraud labels / feedback stats ───────────────────────────────
export const getFeedbackStats = (userId) =>
  riskClient.get(`/risk/users/${userId}/feedback-stats`).then(d);

// ── Phase 4 — Decision engine: merchant config + blacklist ────────────────
export const getMerchantConfig = (merchantId) =>
  adminClient.get(`/admin/merchants/${merchantId}/risk-config`).then(d);

export const getBlacklist = () =>
  adminClient.get("/admin/blacklist").then(d);

export const addBlacklist = (payload) =>
  adminClient.post("/admin/blacklist", payload).then(d);

export const removeBlacklist = (entityId) =>
  adminClient.delete(`/admin/blacklist/${entityId}`).then(d);

// ── Phase 5 — MLOps: models, drift, shadow ───────────────────────────────
export const getModels = () =>
  adminClient.get("/admin/models").then(d);

export const getDriftReport = () =>
  adminClient.get("/admin/drift-report").then(d);

export const getShadowReport = () =>
  adminClient.get("/admin/shadow-report").then(d);

export const triggerDriftRun = () =>
  adminClient.get("/admin/drift-run").then(d);

// ── Phase 6 — Device trust (new endpoint) ────────────────────────────────
export const getDevices = (userId) =>
  riskClient.get(`/risk/users/${userId}/devices`).then(d);

// ── Phase 6 — Graph / network (admin deep-dive) ──────────────────────────
export const getUserNetwork = (userId) =>
  adminClient.get(`/admin/users/${userId}/network`).then(d);

export const getFraudDistance = (userId) =>
  adminClient.get(`/admin/users/${userId}/fraud-distance`).then(d);

export const getFraudRing = (userId) =>
  adminClient.get(`/admin/users/${userId}/fraud-ring`).then(d);

// ── Phase 7 — SHAP explainability ────────────────────────────────────────
export const getExplanation = (txnId) =>
  adminClient.get(`/transactions/${txnId}/explain`).then(d);

export const getSimilarTransactions = (txnId) =>
  adminClient.get(`/transactions/${txnId}/similar`).then(d);

// ── Phase 8 — Feedback flywheel / review queue ───────────────────────────
export const reportFraud = (txnId, notes = "") =>
  riskClient.post(`/transactions/${txnId}/report-fraud`, { notes }).then(d);

// Enriched review queue — includes merchant, amount, reason joined from transactions
export const getEnrichedReviewQueue = (status = "pending", limit = 20, userId = null) =>
  riskClient
    .get("/risk/review-queue", {
      params: { status, limit, ...(userId != null ? { user_id: userId } : {}) },
    })
    .then(d);

export const getFraudShieldLiveEvents = (userId, limit = 20) =>
  riskClient.get(`/fraud-shield/${userId}/live-events`, { params: { limit } }).then(d);

export const getReviewQueue = (params = {}) =>
  adminClient.get("/admin/review-queue", { params }).then(d);

export const getReviewItem = (queueId) =>
  adminClient.get(`/admin/review-queue/${queueId}`).then(d);

export const decideReviewItem = (queueId, resolution, notes = "") =>
  adminClient
    .post(`/admin/review-queue/${queueId}/decide`, { resolution, notes })
    .then(d);

/** Resolve own review-queue item (JWT) — no admin token. */
export const selfResolveReviewQueue = (queueId, { resolution, notes = "" }) =>
  riskClient
    .post(`/risk/review-queue/${queueId}/self-resolve`, { resolution, notes })
    .then(d);

// ── Model status (real trained model metrics) ─────────────────────────────
export const getModelStatus = () =>
  riskClient.get("/risk/model-status").then(d);

// ── Live feed (not yet on backend — graceful stub) ───────────────────────
export const getRiskFeed = (_since) =>
  Promise.reject(new Error("risk-feed endpoint not yet available"));

// ══════════════════════════════════════════════════════════════════════════
// Phase 9 — LLM Investigation Agent
// ══════════════════════════════════════════════════════════════════════════

/** Get the latest investigation for a transaction. */
export const getInvestigation = (txnId) =>
  riskClient.get(`/risk/investigations/${txnId}`).then(d);

/** Manually trigger an LLM investigation for a transaction. */
export const triggerInvestigation = (txnId, userId = null, triggeredBy = "manual") =>
  riskClient
    .post(`/risk/investigations/${txnId}/run`, null, {
      timeout: 90_000,
      params: { ...(userId != null ? { user_id: userId } : {}), triggered_by: triggeredBy },
    })
    .then(d);

/** Get today's Phase 9 LLM budget spend rollup. */
export const getInvestigationBudget = () =>
  adminClient.get("/risk/investigations/budget/today").then(d);

/** Phase 9 health check (public — no admin token required). */
export const getInvestigationHealth = () =>
  riskClient.get("/risk/investigations/health").then(d);

// ══════════════════════════════════════════════════════════════════════════
// Phase 10 — Graph Neural Network
// ══════════════════════════════════════════════════════════════════════════

/** Get GNN training status / embedding inventory. */
export const getGnnStatus = () =>
  adminClient.get("/risk/gnn/status").then(d);

/** Trigger a GNN training run. */
export const triggerGnnTrain = (params = {}) =>
  adminClient.post("/risk/gnn/train", null, { params, timeout: 120_000 }).then(d);

/** Get the GNN embedding for a user. */
export const getGnnEmbedding = (userId) =>
  adminClient.get(`/risk/gnn/users/${userId}/embedding`).then(d);

/** Phase 10 health check (public). */
export const getGnnHealth = () =>
  riskClient.get("/risk/gnn/health").then(d);

// ══════════════════════════════════════════════════════════════════════════
// Phase 11 — Deep Neural Network
// ══════════════════════════════════════════════════════════════════════════

/** Get DNN training status / shadow metrics. */
export const getDnnStatus = () =>
  adminClient.get("/risk/dnn/status").then(d);

/** Trigger a DNN training run. */
export const triggerDnnTrain = () =>
  adminClient.post("/risk/dnn/train", null, { timeout: 90_000 }).then(d);

/** Get DNN shadow evaluation report. */
export const getDnnShadowEvaluation = () =>
  adminClient.get("/risk/dnn/shadow/evaluation").then(d);

/** Run a DNN prediction (POST, requires feature payload). */
export const getDnnPredict = (features) =>
  adminClient.post("/risk/dnn/predict", features).then(d);

/** Phase 11 health check (public). */
export const getDnnHealth = () =>
  riskClient.get("/risk/dnn/health").then(d);

// ══════════════════════════════════════════════════════════════════════════
// Phase 12 — Multi-Model Orchestrator
// ══════════════════════════════════════════════════════════════════════════

/** Get today's aggregated LLM cost dashboard (Phase 9 + 12). */
export const getCostsToday = () =>
  adminClient.get("/risk/orchestrator/costs/today").then(d);

/** Run the orchestrator routing decision for a transaction. */
export const orchestrateDecision = (payload) =>
  adminClient.post("/risk/orchestrator/decide", payload).then(d);

/** Get the orchestration decision record for a transaction. */
export const getOrchestrationDecision = (txnId) =>
  adminClient.get(`/risk/orchestrator/decisions/${txnId}`).then(d);

/** Preview which tier a score would route to (dry-run). */
export const previewOrchestrationRoute = (params = {}) =>
  adminClient.get("/risk/orchestrator/route/preview", { params }).then(d);

/** Phase 12 health check (public). */
export const getOrchestratorHealth = () =>
  riskClient.get("/risk/orchestrator/health").then(d);

// ══════════════════════════════════════════════════════════════════════════
// Business Impact & Trust Score (global analytics)
// ══════════════════════════════════════════════════════════════════════════

/** Get global business impact metrics computed from live DB data. */
export const getBusinessImpact = () =>
  riskClient.get("/business-impact").then(d);

/** Get computed 0-1000 trust score with formula breakdown. */
export const getTrustScore = (userId) =>
  riskClient.get(`/trust-score/${userId}`).then(d);
