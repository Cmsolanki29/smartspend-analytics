/**
 * SmartSpend AI Risk Pipeline — 12-layer protection stack.
 * Each phase maps to a real backend service, migration, and routes file.
 * User-facing surface: FraudShield (`tabId: "fraud"`) with URL `?fraudTab=…`.
 * Source of truth: backend/core/config.py, database/migrations/, backend/routes/.
 */

export type MasteryPhaseMeta = {
  phase: number;
  /** Short name shown inside the node tooltip / detail panel */
  title: string;
  /** Technical one-liner explaining what this layer does */
  nextHint: string;
  /** Category drives connector gradient grouping in the UI */
  category: "data" | "model" | "intelligence" | "ops";
  /** Primary app tab — all phases route to FraudShield */
  tabId: "fraud";
  /** Suggested FraudShield sub-tab when opening this layer from the rail */
  fraudshieldTab: "overview" | "alerts" | "behavior" | "devices" | "investigations" | "live";
};

export const MASTERY_PHASES: readonly MasteryPhaseMeta[] = [
  {
    phase: 1,
    title: "Event Engine",
    nextHint: "Real-time transaction event bus — Redis Streams, durable events log, baseline alerts.",
    category: "data",
    tabId: "fraud",
    fraudshieldTab: "live",
  },
  {
    phase: 2,
    title: "Feature Store",
    nextHint: "Online Redis + offline feature snapshots for point-in-time training and scoring.",
    category: "data",
    tabId: "fraud",
    fraudshieldTab: "behavior",
  },
  {
    phase: 3,
    title: "Fraud Classifier",
    nextHint: "XGBoost supervised fraud detection — fraud labels, fraud_feedback table, calibration.",
    category: "model",
    tabId: "fraud",
    fraudshieldTab: "overview",
  },
  {
    phase: 4,
    title: "Decision Engine",
    nextHint: "Rule-based gate: merchant thresholds, blacklisted entities, risk policy extensions.",
    category: "model",
    tabId: "fraud",
    fraudshieldTab: "overview",
  },
  {
    phase: 5,
    title: "MLOps & Drift",
    nextHint: "Model registry stages, PSI drift detection, shadow dual-scoring, canary promotion.",
    category: "ops",
    tabId: "fraud",
    fraudshieldTab: "overview",
  },
  {
    phase: 6,
    title: "Graph Signals",
    nextHint: "Heterogeneous graph features — device, IP, card, user network signals & fraud distance.",
    category: "data",
    tabId: "fraud",
    fraudshieldTab: "devices",
  },
  {
    phase: 7,
    title: "Explainability",
    nextHint: "On-demand SHAP explanations for every scored transaction, surfaced on review.",
    category: "intelligence",
    tabId: "fraud",
    fraudshieldTab: "alerts",
  },
  {
    phase: 8,
    title: "Feedback Loop",
    nextHint: "Analyst review queue, user fraud reports, chargeback webhooks — feeds model retraining.",
    category: "ops",
    tabId: "fraud",
    fraudshieldTab: "alerts",
  },
  {
    phase: 9,
    title: "LLM Investigator",
    nextHint: "Groq-powered AI agent investigates high-risk transactions, persists to risk_investigations.",
    category: "intelligence",
    tabId: "fraud",
    fraudshieldTab: "investigations",
  },
  {
    phase: 10,
    title: "GNN Embeddings",
    nextHint: "GraphSAGE heterogeneous graph training — user & entity embeddings for deep link analysis.",
    category: "intelligence",
    tabId: "fraud",
    fraudshieldTab: "overview",
  },
  {
    phase: 11,
    title: "DNN Shadow",
    nextHint: "Multi-branch deep network running shadow-first alongside XGBoost with blend weight tuning.",
    category: "model",
    tabId: "fraud",
    fraudshieldTab: "overview",
  },
  {
    phase: 12,
    title: "Orchestrator",
    nextHint: "Multi-model orchestrator + LLM-as-Judge: tier routing, final decisions, orchestration_decisions log.",
    category: "intelligence",
    tabId: "fraud",
    fraudshieldTab: "overview",
  },
] as const;

export function getMasteryPhase(n: number): MasteryPhaseMeta | undefined {
  return MASTERY_PHASES.find((p) => p.phase === n);
}

/** Short display name for a category group */
export const CATEGORY_LABELS: Record<MasteryPhaseMeta["category"], string> = {
  data: "Data",
  model: "Models",
  intelligence: "Intelligence",
  ops: "Ops",
};
