/**
 * TrustCenter — 12-Phase AI fraud protection showpiece page.
 * Shows all 12 phases, trust score gauge, live engine status,
 * Phase 9-12 (2026 parity) status panel, and quick-action links.
 */

import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  ShieldCheck, ShieldOff, Zap, ArrowRight, BarChart2, Bell,
  User, Fingerprint, TrendingUp, DollarSign, Bot, Share2,
  Layers, GitMerge, CheckCircle2, XCircle, AlertTriangle,
} from "lucide-react";
import { TrustScoreGauge } from "../../components/risk/TrustScoreGauge";
import { PhaseCard } from "../../components/risk/PhaseCard";
import { RiskLiveTicker } from "../../components/risk/RiskLiveTicker";
import { useRisk } from "../../contexts/RiskContext";
import { PHASES } from "../../utils/risk/phaseConfig";
import { fmtRelativeTime, fmtCurrency } from "../../utils/risk/formatters";
import {
  getGnnHealth,
  getDnnHealth,
  getOrchestratorHealth,
  getInvestigationHealth,
} from "../../services/riskApi";

function EngineStatusBanner({ healthy, lastCheckedAt }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      className={`flex items-center gap-3 px-4 py-3 rounded-xl border text-sm font-medium ${
        healthy
          ? "bg-green-50 border-green-200 text-green-700"
          : "bg-gray-50 border-gray-200 text-gray-500"
      }`}
    >
      {healthy ? <ShieldCheck size={18} /> : <ShieldOff size={18} />}
      <span>
        {healthy
          ? "12-Phase AI Fraud Engine is active and protecting your account"
          : "Risk engine is currently offline — basic protection still active"}
      </span>
      {lastCheckedAt && (
        <span className="ml-auto text-xs opacity-60">
          checked {fmtRelativeTime(lastCheckedAt)}
        </span>
      )}
    </motion.div>
  );
}

function QuickActionCard({ icon: Icon, title, subtitle, color, bg, onClick }) {
  return (
    <motion.button
      type="button"
      onClick={onClick}
      whileHover={{ scale: 1.02, y: -2 }}
      whileTap={{ scale: 0.98 }}
      className="flex items-center gap-3 p-4 rounded-2xl border border-gray-100 bg-white shadow-sm hover:shadow-md transition-shadow text-left w-full"
    >
      <div
        className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
        style={{ background: bg }}
      >
        <Icon size={20} style={{ color }} />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-gray-900">{title}</p>
        <p className="text-xs text-gray-400 truncate">{subtitle}</p>
      </div>
      <ArrowRight size={16} className="text-gray-300 shrink-0" />
    </motion.button>
  );
}

/** Small status pill for Phase 9-12 panel */
function StatusPill({ ok, label }) {
  return (
    <span
      className={`inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full ${
        ok === null
          ? "bg-yellow-100 text-yellow-700"
          : ok
          ? "bg-green-100 text-green-700"
          : "bg-red-100 text-red-700"
      }`}
    >
      {ok === null ? (
        <AlertTriangle size={10} />
      ) : ok ? (
        <CheckCircle2 size={10} />
      ) : (
        <XCircle size={10} />
      )}
      {label}
    </span>
  );
}

/** Phase 9-12 "2026 parity" live status panel */
function AdvancedPhasesPanel({ userId }) {
  const [costs, setCosts] = useState(null);
  const [gnn, setGnn] = useState(null);
  const [dnn, setDnn] = useState(null);
  const [invCount, setInvCount] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      const [inv, g, d, c] = await Promise.allSettled([
        getInvestigationHealth(),
        getGnnHealth(),
        getDnnHealth(),
        getOrchestratorHealth(),
      ]);
      if (cancelled) return;
      // Phase 9 health uses `feature_flag_enabled`; 10-12 use `enabled`
      setInvCount(
        inv.status === "fulfilled" ? (inv.value?.feature_flag_enabled ?? false) : null
      );
      setGnn(g.status === "fulfilled" ? g.value : null);   // has `enabled`, `embed_dim`, etc.
      setDnn(d.status === "fulfilled" ? d.value : null);   // has `enabled`, `promoted`, `model_loaded`
      setCosts(c.status === "fulfilled" ? c.value : null); // has `enabled`, `judge_enabled`
      setLoading(false);
    })();
    return () => { cancelled = true; };
  }, [userId]);

  const rows = [
    {
      icon: Bot,
      color: "#a855f7",
      label: "Phase 9 · LLM Agent",
      badge: "2026",
      status: !!invCount,
      statusLabel: invCount === null ? "Unavailable" : invCount ? "Enabled" : "Disabled",
      detail: invCount === null ? "Backend offline" : invCount ? "Auto-investigates high-risk transactions" : "Set PHASE_9_AGENT_ENABLED=true",
    },
    {
      icon: Share2,
      color: "#0ea5e9",
      label: "Phase 10 · GNN",
      badge: "2026",
      status: gnn !== null ? gnn.feature_flag_enabled : null,
      statusLabel: gnn === null ? "Unavailable" : gnn.feature_flag_enabled ? "Enabled" : "Disabled",
      detail: gnn
        ? `GraphSAGE · ${gnn.embed_dim ?? 64}-dim · ${gnn.training_days ?? 90}-day window`
        : "Backend offline",
    },
    {
      icon: Layers,
      color: "#14b8a6",
      label: "Phase 11 · DNN (shadow)",
      badge: "2026",
      status: dnn !== null ? dnn.enabled : null,
      statusLabel: dnn === null ? "Unavailable" : dnn.enabled ? "Shadow active" : "Disabled",
      detail: dnn
        ? `Multi-branch DNN · promoted=${dnn.promoted ? "yes" : "no"} · model=${dnn.model_loaded ? "loaded" : "not trained"}`
        : "Backend offline",
    },
    {
      icon: GitMerge,
      color: "#f43f5e",
      label: "Phase 12 · Orchestrator",
      badge: "2026",
      status: costs !== null ? costs.enabled : null,
      statusLabel: costs === null ? "Unavailable" : costs.enabled ? "Active" : "Disabled",
      detail: costs
        ? `Tiers 0-3 routing · judge=${costs.judge_enabled ? "on" : "off"}`
        : "Backend offline",
    },
  ];

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.15 }}
      className="rounded-2xl border border-purple-500/20 bg-gradient-to-br from-purple-900/20 via-exiqo-dark/40 to-pink-900/10 p-5 backdrop-blur-sm"
    >
      <div className="flex items-center justify-between mb-4">
        <p className="text-xs uppercase tracking-wider text-purple-300 font-semibold">
          2026 Parity Phases · Live Status
        </p>
        {loading && (
          <span className="text-[10px] text-exiqo-glow/40 animate-pulse">Fetching…</span>
        )}
      </div>
      <div className="space-y-3">
        {rows.map(({ icon: Icon, color, label, badge, status, statusLabel, detail }) => (
          <div key={label} className="flex items-center gap-3">
            <div
              className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
              style={{ background: `${color}22` }}
            >
              <Icon size={16} style={{ color }} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-exiqo-glow/90">{label}</span>
                <span className="text-[9px] font-bold bg-purple-500/20 text-purple-300 px-1.5 py-0.5 rounded uppercase tracking-wider">
                  {badge}
                </span>
              </div>
              <p className="text-[11px] text-exiqo-glow/40 truncate">{detail}</p>
            </div>
            <StatusPill ok={loading ? null : status} label={loading ? "…" : statusLabel} />
          </div>
        ))}
      </div>
    </motion.div>
  );
}

const TrustCenter = ({ userId, onNavigate }) => {
  const { healthy, dbConnected, mlReady, version, lastCheckedAt } = useRisk();

  return (
    <div className="max-w-3xl mx-auto space-y-6 pb-8">
      {/* Page header */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-start justify-between"
      >
        <div>
          <h2 className="text-2xl font-bold text-white">Trust Center</h2>
          <p className="text-exiqo-glow/60 text-sm mt-1">
            12-phase AI fraud protection — 2026 industry standard
          </p>
        </div>
        {version && (
          <span className="text-xs text-exiqo-glow/40 bg-white/5 px-2 py-1 rounded-lg border border-white/10">
            v{version}
          </span>
        )}
      </motion.div>

      {/* Engine status banner */}
      <EngineStatusBanner healthy={healthy} lastCheckedAt={lastCheckedAt} />

      {/* Hero stats */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="rounded-2xl border border-white/10 bg-gradient-to-br from-exiqo-purple/15 via-exiqo-dark/40 to-exiqo-pink/10 p-5 backdrop-blur-sm"
      >
        <p className="text-xs uppercase tracking-wider text-exiqo-glow/60 font-semibold mb-3">
          Protection Summary · This Month
        </p>
        <div className="grid grid-cols-3 gap-3">
          <div className="text-center">
            <div className="flex items-center justify-center gap-1.5 mb-1">
              <ShieldCheck size={14} className="text-green-400" />
              <p className="text-xs text-exiqo-glow/60 uppercase tracking-wide">Threats Blocked</p>
            </div>
            <p className="text-3xl font-bold text-green-400">12</p>
            <p className="text-[10px] text-exiqo-glow/40 mt-0.5">↑ 3 vs last month</p>
          </div>
          <div className="text-center border-x border-white/10">
            <div className="flex items-center justify-center gap-1.5 mb-1">
              <DollarSign size={14} className="text-yellow-400" />
              <p className="text-xs text-exiqo-glow/60 uppercase tracking-wide">Money Saved</p>
            </div>
            <p className="text-3xl font-bold text-yellow-400">{fmtCurrency(48500)}</p>
            <p className="text-[10px] text-exiqo-glow/40 mt-0.5">across 7 fraud attempts</p>
          </div>
          <div className="text-center">
            <div className="flex items-center justify-center gap-1.5 mb-1">
              <TrendingUp size={14} className="text-pink-400" />
              <p className="text-xs text-exiqo-glow/60 uppercase tracking-wide">Detection Rate</p>
            </div>
            <p className="text-3xl font-bold text-pink-400">94.7%</p>
            <p className="text-[10px] text-exiqo-glow/40 mt-0.5">XGBoost + DNN + GNN</p>
          </div>
        </div>
      </motion.div>

      {/* Phase 9-12 live status panel */}
      <AdvancedPhasesPanel userId={userId} />

      {/* Trust score + engine health side-by-side */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5 flex flex-col items-center">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">Financial Trust Score</h3>
          <TrustScoreGauge score={742} />
          <p className="text-xs text-gray-400 text-center mt-2">
            Based on spending patterns, repayment history, and fraud signals
          </p>
        </div>

        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5 space-y-3">
          <h3 className="text-sm font-semibold text-gray-700">Engine Status</h3>
          {[
            { label: "API Gateway",          ok: true },
            { label: "Database Pool",         ok: dbConnected },
            { label: "XGBoost (prod)",        ok: mlReady },
            { label: "Redis Event Bus",       ok: healthy },
            { label: "SHAP Explainer",        ok: mlReady },
            { label: "Phase 9 LLM Agent",     ok: healthy },
            { label: "Phase 10 GNN",          ok: healthy },
            { label: "Phase 11 DNN (shadow)", ok: healthy },
            { label: "Phase 12 Orchestrator", ok: healthy },
          ].map(({ label, ok }) => (
            <div key={label} className="flex items-center gap-2 text-sm">
              <span
                className={`w-2 h-2 rounded-full shrink-0 ${ok ? "bg-green-400" : "bg-gray-300"}`}
              />
              <span className={ok ? "text-gray-700" : "text-gray-400"}>{label}</span>
              <span className={`ml-auto text-xs font-medium ${ok ? "text-green-600" : "text-gray-400"}`}>
                {ok ? "Online" : "Offline"}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Live ticker */}
      <div className="bg-white/5 border border-white/10 rounded-2xl p-4">
        <p className="text-xs text-exiqo-glow/40 mb-2 uppercase tracking-wider">
          Live Transaction Feed
        </p>
        <RiskLiveTicker />
      </div>

      {/* Quick actions */}
      <div>
        <h3 className="text-sm font-semibold text-white mb-3 uppercase tracking-wider opacity-60">
          Deep-dive analysis
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <QuickActionCard
            icon={BarChart2}
            title="AI Performance"
            subtitle="Model accuracy, drift, shadow tests"
            color="#6366f1"
            bg="#eef2ff"
            onClick={() => onNavigate?.("ai-performance")}
          />
          <QuickActionCard
            icon={Bell}
            title="Alerts Center"
            subtitle="Review queue · fraud reports"
            color="#f97316"
            bg="#fff7ed"
            onClick={() => onNavigate?.("alerts-center")}
          />
          <QuickActionCard
            icon={User}
            title="Behavior Profile"
            subtitle="Login patterns · locations · anomalies · Phase 2"
            color="#8b5cf6"
            bg="#f5f3ff"
            onClick={() => onNavigate?.("behavior-profile")}
          />
          <QuickActionCard
            icon={Fingerprint}
            title="Device Trust"
            subtitle="Device fingerprinting · fraud ring detection · Phase 6"
            color="#ec4899"
            bg="#fdf2f8"
            onClick={() => onNavigate?.("device-trust")}
          />
          <QuickActionCard
            icon={Zap}
            title="Real-time Events"
            subtitle="Live event bus stats · Phase 1"
            color="#3b82f6"
            bg="#eff6ff"
            onClick={() => onNavigate?.("fraud")}
          />
          <QuickActionCard
            icon={ShieldCheck}
            title="Fraud Shield"
            subtitle="Anomaly detector · full analysis"
            color="#10b981"
            bg="#ecfdf5"
            onClick={() => onNavigate?.("fraud")}
          />
        </div>
      </div>

      {/* Phase cards — all 12 */}
      <div>
        <h3 className="text-sm font-semibold text-white mb-3 uppercase tracking-wider opacity-60">
          The 12 Phases
        </h3>
        <div className="space-y-2">
          {PHASES.map((phase, i) => (
            <PhaseCard key={phase.id} phase={phase} index={i} />
          ))}
        </div>
      </div>
    </div>
  );
};

export default TrustCenter;
