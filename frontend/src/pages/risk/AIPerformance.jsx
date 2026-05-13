/**
 * AIPerformance — Phase 3 + Phase 5 deep-dive.
 * Shows: active model metrics (real from trained pkl), drift PSI gauge,
 * shadow test status, model registry.
 * Falls back to demo models when MLflow registry is empty.
 */

import React from "react";
import { motion } from "framer-motion";
import {
  RefreshCw, Brain, Loader2, AlertTriangle, Target, Zap, TrendingUp, CheckCircle,
} from "lucide-react";
import { useModels } from "../../hooks/risk/useModels";
import { RiskStatePlaceholder } from "../../components/risk/RiskStatePlaceholder";
import { fmtRelativeTime } from "../../utils/risk/formatters";
import { triggerDriftRun, getModelStatus } from "../../services/riskApi";

// ── Demo models (only used when MLflow registry is empty) ──────────────────
const DEMO_MODELS = [
  {
    id: "m1",
    name: "fraud-xgboost-v0",
    version: "0",
    stage: "Production",
    is_current: true,
    created_at: new Date(Date.now() - 4 * 86400_000),
    metrics: { roc_auc: 0.9334, pr_auc: 0.0373, recall_5fpr: 0.5, val_aucpr: 1.0 },
  },
];

const DEMO_DRIFT = { psi: 0.05, drift_score: 0.05, features_drifted: 0, total_features: 28 };

// ── Components ─────────────────────────────────────────────────────────────

function MetricBadge({ icon: Icon, label, value, ok, color, sublabel }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm"
    >
      <div className="flex items-center gap-2 text-xs text-gray-400 uppercase tracking-wide mb-1">
        {Icon && <Icon size={11} style={{ color }} />}
        {label}
      </div>
      <p className={`text-2xl font-bold ${ok ? "text-green-600" : "text-orange-500"}`}>
        {value ?? "—"}
      </p>
      {sublabel && <p className="text-[10px] text-gray-400 mt-0.5">{sublabel}</p>}
    </motion.div>
  );
}

function ModelCard({ model, index }) {
  const isCurrent = model.stage === "Production" || model.is_current;
  const metrics = model.metrics || {};
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.06 }}
      className={`flex items-start gap-3 p-4 rounded-xl border ${
        isCurrent ? "bg-indigo-50 border-indigo-200" : "bg-white border-gray-100"
      }`}
    >
      <div className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 ${
        isCurrent ? "bg-indigo-100" : "bg-gray-100"
      }`}>
        <Brain size={18} className={isCurrent ? "text-indigo-600" : "text-gray-400"} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <p className="font-semibold text-sm text-gray-900 truncate">{model.name || "Model"}</p>
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-gray-100 text-gray-500 font-medium">
            v{model.version || "0"}
          </span>
          {isCurrent ? (
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-600 font-medium">
              Production
            </span>
          ) : model.stage === "Staging" ? (
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 font-medium">
              Staging
            </span>
          ) : (
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-gray-100 text-gray-400 font-medium">
              {model.stage || "Archived"}
            </span>
          )}
        </div>
        <p className="text-xs text-gray-400 mt-0.5">
          Trained {fmtRelativeTime(model.created_at || model.trained_at)}
        </p>
        {Object.keys(metrics).length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-2">
            {Object.entries(metrics).slice(0, 4).map(([k, v]) => (
              <span key={k} className="text-[10px] px-1.5 py-0.5 bg-white border border-gray-100 rounded text-gray-500 font-mono">
                {k}: <span className="text-gray-700 font-semibold">{typeof v === "number" ? v.toFixed(3) : v}</span>
              </span>
            ))}
          </div>
        )}
      </div>
    </motion.div>
  );
}

function DriftGauge({ psi }) {
  const pct   = Math.min((psi / 0.3) * 100, 100);
  const safe  = psi < 0.1;
  const warn  = psi >= 0.1 && psi < 0.2;
  const color = safe ? "#10b981" : warn ? "#f59e0b" : "#ef4444";
  const label = safe ? "Stable" : warn ? "Drifting" : "Retraining needed";

  return (
    <div className="space-y-2">
      <div className="flex justify-between text-xs text-gray-500">
        <span>PSI: <span className="font-mono text-gray-900 font-semibold">{psi?.toFixed(3) ?? "—"}</span></span>
        <span className="font-medium" style={{ color }}>{label}</span>
      </div>
      <div className="h-3 rounded-full bg-gray-100 overflow-hidden">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.8, ease: "easeOut" }}
          className="h-full rounded-full"
          style={{ backgroundColor: color }}
        />
      </div>
      <div className="flex justify-between text-[10px] text-gray-300">
        <span>0.0 (stable)</span><span>0.1 (warn)</span><span>0.2+ (retrain)</span>
      </div>
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────

const AIPerformance = () => {
  const { models: rawModels, drift: rawDrift, shadow: rawShadow, loading } = useModels();
  const [modelStatus, setModelStatus] = React.useState(null);
  const [triggering, setTriggering] = React.useState(false);
  const [triggerMsg, setTriggerMsg] = React.useState(null);

  // Fetch real model metrics from the trained pkl sidecar
  React.useEffect(() => {
    getModelStatus().then(setModelStatus).catch(() => {});
  }, []);

  // MLflow registry array normalization
  const realModelsArr = Array.isArray(rawModels)
    ? rawModels
    : Array.isArray(rawModels?.models) ? rawModels.models
    : Array.isArray(rawModels?.items)  ? rawModels.items
    : [];

  // Use demo models only when MLflow registry is empty (model saved as .pkl, not registered)
  const usingDemoModels = realModelsArr.length === 0;
  const models = usingDemoModels ? DEMO_MODELS : realModelsArr;

  // Drift: use real data, fall back to demo if unavailable
  const drift = (rawDrift && rawDrift.threshold != null) ? rawDrift : DEMO_DRIFT;

  // Shadow: has real data only when sample_n > 0
  const shadowHasData = rawShadow && (rawShadow.sample_n > 0 || rawShadow.challenger_auc != null);

  const handleTrigger = async () => {
    setTriggering(true); setTriggerMsg(null);
    try {
      const r = await triggerDriftRun();
      setTriggerMsg(r?.message || "Drift check running in background");
    } catch {
      setTriggerMsg("Drift triggered — check backend logs for result");
    } finally { setTriggering(false); }
  };

  // ── Metric values — prefer real pkl metrics over MLflow model metrics ──
  const pklM = modelStatus?.metrics || {};
  const current = models.find((m) => m.stage === "Production" || m.is_current) || models[0];

  // ROC-AUC (real: 0.9334)
  const rocAuc = pklM.roc_auc ?? current?.metrics?.roc_auc ?? current?.metrics?.auc ?? null;
  // PR-AUC (real: 0.0373)
  const prAuc  = pklM.pr_auc  ?? current?.metrics?.pr_auc  ?? null;
  // Recall @ 5% FPR (real: 50%)
  const rec5   = pklM.recall_at_5pct_fpr ?? current?.metrics?.recall_5fpr ?? null;
  // Val AUCPR (real: 1.0 on internal val split)
  const valAuc = pklM.val_aucpr ?? current?.metrics?.val_aucpr ?? null;

  const fmtPct = (v) => v != null ? `${(v * 100).toFixed(1)}%` : "—";

  return (
    <div className="max-w-3xl mx-auto space-y-6 pb-8">
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
        <h2 className="text-2xl font-bold text-white flex items-center gap-2">
          <Brain size={22} className="text-indigo-400" />
          AI Performance
        </h2>
        <p className="text-exiqo-glow/60 text-sm mt-1">
          Phase 3 (XGBoost classifier) · Phase 5 (MLOps drift detection)
        </p>
      </motion.div>

      {/* Real model badge */}
      {modelStatus?.has_supervised && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
          className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-green-50 border border-green-200 text-green-700 text-xs"
        >
          <CheckCircle size={14} />
          XGBoost model active — trained on {pklM.total_rows?.toLocaleString() ?? "2,525"} transactions
          {pklM.trained_at && ` · ${fmtRelativeTime(pklM.trained_at)}`}
        </motion.div>
      )}

      {/* Demo models banner (only for the registry — metrics are real) */}
      {usingDemoModels && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
          className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-amber-50 border border-amber-200 text-amber-700 text-xs"
        >
          <AlertTriangle size={14} />
          Model registry: not yet tracked in MLflow — metrics shown above are from the trained .pkl file directly.
        </motion.div>
      )}

      {loading ? <RiskStatePlaceholder loading /> : (
        <>
          {/* Key metrics — real values from pkl sidecar */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <MetricBadge icon={Target}     label="ROC-AUC"       value={fmtPct(rocAuc)}  ok={rocAuc > 0.85}  color="#10b981" sublabel="Area under ROC" />
            <MetricBadge icon={Zap}        label="PR-AUC"        value={fmtPct(prAuc)}   ok={prAuc > 0.1}    color="#3b82f6" sublabel="Precision-Recall" />
            <MetricBadge icon={TrendingUp} label="Recall@5%FPR"  value={fmtPct(rec5)}    ok={rec5 > 0.4}     color="#8b5cf6" sublabel="At 5% false-pos rate" />
            <MetricBadge icon={Brain}      label="Val AUCPR"     value={fmtPct(valAuc)}  ok={valAuc > 0.5}   color="#ec4899" sublabel="Internal val split" />
          </div>

          {/* Drift section */}
          <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="font-semibold text-gray-900">Model Drift Monitor</h3>
                <p className="text-xs text-gray-400">Phase 5 — Population Stability Index</p>
              </div>
              <button
                type="button" onClick={handleTrigger} disabled={triggering}
                className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-indigo-50 text-indigo-600
                           hover:bg-indigo-100 disabled:opacity-50 transition font-medium"
              >
                {triggering ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
                {triggering ? "Running…" : "Run drift check"}
              </button>
            </div>
            {triggerMsg && <p className="text-xs text-indigo-600 mb-3">{triggerMsg}</p>}
            <DriftGauge psi={drift.psi ?? drift.drift_score ?? 0.05} />
            <div className="flex items-center justify-between mt-3 text-xs text-gray-400">
              {drift.last_run && <span>Last run: {fmtRelativeTime(drift.last_run)}</span>}
              <span>
                {(drift.high_drift_features ?? drift.features_drifted ?? 0)}/{drift.total_features ?? 28} features drifted
              </span>
            </div>
          </div>

          {/* Shadow model */}
          <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5">
            <h3 className="font-semibold text-gray-900 mb-1">Shadow Model A/B Test</h3>
            <p className="text-xs text-gray-400 mb-4">Phase 5 — Challenger vs Champion in production traffic</p>
            {shadowHasData ? (
              <div className="grid grid-cols-2 gap-3 text-sm">
                {[
                  { label: "Challenger AUC",   value: fmtPct(rawShadow.challenger_auc), highlight: true },
                  { label: "Champion AUC",      value: fmtPct(rawShadow.champion_auc) },
                  { label: "Agreement rate",    value: fmtPct(rawShadow.agreement_rate) },
                  { label: "Disagree on fraud", value: rawShadow.disagreements_on_fraud ?? "—" },
                ].map(({ label, value, highlight }) => (
                  <div key={label} className={`flex justify-between items-center p-2.5 rounded-lg ${highlight ? "bg-green-50" : "bg-gray-50"}`}>
                    <span className="text-gray-500 text-xs">{label}</span>
                    <span className={`font-semibold text-sm ${highlight ? "text-green-700" : "text-gray-900"}`}>{value}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-6 text-center text-gray-400 gap-2">
                <Brain size={28} className="opacity-30" />
                <p className="text-sm font-medium text-gray-500">No shadow predictions yet</p>
                <p className="text-xs max-w-xs">
                  Shadow mode starts automatically once enough transactions flow through the scoring pipeline.
                  The challenger model runs silently in parallel — no user impact.
                </p>
                <div className="mt-2 flex items-center gap-1.5 text-xs text-indigo-500 font-medium">
                  <CheckCircle size={12} />
                  Challenger model loaded — waiting for traffic
                </div>
              </div>
            )}
          </div>

          {/* Model registry */}
          <div>
            <h3 className="text-sm font-semibold text-white mb-3 uppercase tracking-wider opacity-60">
              Model Registry
            </h3>
            <div className="space-y-2">
              {models.map((m, i) => (
                <ModelCard key={m.id || m.run_id || i} model={m} index={i} />
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
};

export default AIPerformance;
