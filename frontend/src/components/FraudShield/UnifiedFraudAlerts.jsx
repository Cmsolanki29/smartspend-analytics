/**
 * UnifiedFraudAlerts — single surface for FraudShield merged alerts + Phase 8 review queue.
 * Primary data: GET /fraud-shield/{userId}/alerts; enriched/deduped with GET /risk/review-queue?status=all.
 */

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ShieldAlert,
  ShieldCheck,
  CheckCircle2,
  Flag,
  Loader2,
  RefreshCw,
  Inbox,
  ExternalLink,
  Phone,
} from "lucide-react";
import { useViewMode } from "../../context/ViewModeContext";
import {
  getFraudShieldAlerts,
  postFraudShieldAlertAction,
  postFraudShieldAlertActionByTransaction,
} from "../../services/api";
import { fraudAlertDisplayLabel, fraudSeverityFromScore } from "../../utils/fraudLabels";
import {
  getEnrichedReviewQueue,
  getInvestigation,
  selfResolveReviewQueue,
  triggerInvestigation,
} from "../../services/riskApi";
import { useFeedbackStats } from "../../hooks/risk/useFeedbackStats";
import { useToast } from "../common/Toast";
import { ErrorCard } from "../common/ErrorCard";
import { SkeletonCard } from "../common/SkeletonCard";
import { AlertDrawer } from "./AlertDrawer";
import { fmtCurrency, fmtRelativeTime } from "../../utils/risk/formatters";

const SEVERITY_FILTERS = ["ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW"];

const SEVERITY_COLORS = {
  CRITICAL: { bg: "bg-red-900/60", text: "text-red-300", border: "border-red-500/50" },
  HIGH: { bg: "bg-orange-900/60", text: "text-orange-300", border: "border-orange-500/50" },
  MEDIUM: { bg: "bg-yellow-900/60", text: "text-yellow-300", border: "border-yellow-500/50" },
  LOW: { bg: "bg-gray-800/60", text: "text-gray-400", border: "border-gray-600/50" },
};

function severityLabelFromScore(score) {
  const s = Number(score) || 0;
  if (s < 50) return "LOW";
  return fraudSeverityFromScore(s);
}

function getSeverityKey(row) {
  const u = String(row.severity || "").toUpperCase();
  if (["CRITICAL", "HIGH", "MEDIUM", "LOW"].includes(u)) return u;
  return severityLabelFromScore(row.riskScore);
}

function buildUnifiedRows(alerts, queueItems) {
  const queueByTxn = new Map();
  for (const q of queueItems || []) {
    const tid = Number(q.transaction_id);
    if (!Number.isFinite(tid)) continue;
    const cur = queueByTxn.get(tid);
    const prefer =
      !cur ||
      (q.status === "pending" && cur.status !== "pending") ||
      String(q.created_at || "") > String(cur.created_at || "");
    if (prefer) queueByTxn.set(tid, q);
  }

  const usedTxn = new Set();
  const rows = [];

  for (const a of alerts || []) {
    const tid = a.transaction_id != null ? Number(a.transaction_id) : null;
    const q = tid != null && Number.isFinite(tid) ? queueByTxn.get(tid) : null;
    const sev = String(a.severity || "").toUpperCase();
    const severity = ["CRITICAL", "HIGH", "MEDIUM", "LOW"].includes(sev)
      ? sev
      : severityLabelFromScore(a.risk_score);
    rows.push({
      key: tid != null && Number.isFinite(tid) ? `txn-${tid}` : `alert-${a.id}`,
      alertId: typeof a.id === "number" ? a.id : null,
      transactionId: tid != null && Number.isFinite(tid) ? tid : null,
      queueId: q?.id ?? null,
      merchant: a.merchant || q?.merchant || "—",
      amount: Number(a.amount_at_risk ?? q?.amount ?? 0),
      date: a.created_at || q?.transaction_date || q?.created_at,
      riskScore: Number(a.risk_score ?? q?.score ?? 0),
      severity,
      pattern: a.pattern_matched || q?.anomaly_reason || "",
      alertType: a.alert_type || (a.source === "transaction" ? "ML_ANOMALY" : ""),
      hinglish: a.hinglish_explanation || "",
      userAction: String(a.user_action || "PENDING").toUpperCase(),
      paymentMethod: q?.payment_method || null,
      sourceLabel:
        a.source === "fraud_alerts"
          ? "Fraud alert (saved)"
          : a.source === "transaction"
            ? "Live scored"
            : "FraudShield",
      queueStatus: q?.status ?? null,
      queueResolution: q?.resolution ?? null,
      notes: q?.notes || "",
    });
    if (tid != null && Number.isFinite(tid)) usedTxn.add(tid);
  }

  for (const q of queueItems || []) {
    const tid = Number(q.transaction_id);
    if (!Number.isFinite(tid) || usedTxn.has(tid)) continue;
    usedTxn.add(tid);
    const sev = String(q.risk_level || "MEDIUM").toUpperCase();
    rows.push({
      key: `txn-${tid}-q`,
      alertId: null,
      transactionId: tid,
      queueId: q.id,
      merchant: q.merchant || "—",
      amount: Number(q.amount || 0),
      date: q.transaction_date || q.created_at,
      riskScore: Number(q.score || 0),
      severity: ["CRITICAL", "HIGH", "MEDIUM", "LOW"].includes(sev) ? sev : "MEDIUM",
      pattern: q.anomaly_reason || "",
      hinglish: "",
      userAction: "PENDING",
      paymentMethod: q.payment_method,
      sourceLabel: "Review queue",
      queueStatus: q.status,
      queueResolution: q.resolution,
      notes: q.notes || "",
    });
  }

  rows.sort((a, b) => b.riskScore - a.riskScore || String(b.date || "").localeCompare(String(a.date || "")));
  return rows;
}

function queuePending(row) {
  const s = String(row.queueStatus || "").toLowerCase();
  return s === "pending" || s === "in_review";
}

function investigationStatusLabel(row, inv) {
  const res = String(row.queueResolution || "").toLowerCase();
  if (res === "fraud") return "FRAUD_CONFIRMED";
  if (res === "legitimate") return "LEGITIMATE";
  if (queuePending(row)) return "PENDING";
  const qs = String(row.queueStatus || "").toLowerCase();
  if (qs === "resolved" && !row.queueResolution && inv?.decision) {
    return String(inv.decision).toUpperCase();
  }
  if (inv?.decision) return String(inv.decision).toUpperCase();
  return null;
}

function isDemoTxnId(id) {
  if (id == null) return false;
  return /^TXN-99/i.test(String(id));
}

const UnifiedFraudAlerts = ({ userId, onAlertsChanged }) => {
  const { viewMode } = useViewMode();
  const { showToast } = useToast();
  const { data: realStats } = useFeedbackStats();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actingKey, setActingKey] = useState(null);
  const [severityFilter, setSeverityFilter] = useState("ALL");
  const [drawerRow, setDrawerRow] = useState(null);
  const [investigations, setInvestigations] = useState({});

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [alRes, qRes] = await Promise.all([
        getFraudShieldAlerts(userId, viewMode),
        getEnrichedReviewQueue("all", 100, userId).catch(() => ({ items: [] })),
      ]);
      const alerts = (alRes?.alerts || []).filter((a) => Number(a.risk_score || 0) >= 50);
      const queueItems = (qRes?.items ?? (Array.isArray(qRes) ? qRes : [])).filter(
        (q) => Number(q.score || q.risk_score || 0) >= 50
      );
      setRows(buildUnifiedRows(alerts, queueItems));
    } catch (e) {
      setError(e.message || "Failed to load alerts");
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [userId, viewMode]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const handler = () => load();
    window.addEventListener("smartspend:data-updated", handler);
    window.addEventListener("dashboardModeChanged", handler);
    return () => {
      window.removeEventListener("smartspend:data-updated", handler);
      window.removeEventListener("dashboardModeChanged", handler);
    };
  }, [load]);

  const txnIdsForInv = useMemo(
    () =>
      rows
        .map((r) => r.transactionId)
        .filter((id) => id && !isDemoTxnId(id)),
    [rows]
  );

  useEffect(() => {
    if (!txnIdsForInv.length) return;
    let cancelled = false;
    (async () => {
      const results = await Promise.allSettled(txnIdsForInv.map((id) => getInvestigation(id)));
      if (cancelled) return;
      setInvestigations((prev) => {
        const next = { ...prev };
        txnIdsForInv.forEach((id, i) => {
          const r = results[i];
          if (r.status === "fulfilled") next[id] = r.value || null;
          else next[id] = null;
        });
        return next;
      });
    })();
    return () => {
      cancelled = true;
    };
  }, [txnIdsForInv]);

  const refreshOneInvestigation = useCallback(async (txnId) => {
    if (!txnId || isDemoTxnId(txnId)) return;
    setInvestigations((prev) => ({ ...prev, [txnId]: undefined }));
    try {
      const value = await getInvestigation(txnId);
      setInvestigations((prev) => ({ ...prev, [txnId]: value || null }));
    } catch {
      setInvestigations((prev) => ({ ...prev, [txnId]: null }));
    }
  }, []);

  const triggerOneInvestigation = useCallback(
    async (txnId) => {
      if (!txnId || isDemoTxnId(txnId)) return;
      setInvestigations((prev) => ({ ...prev, [txnId]: undefined }));
      try {
        const value = await triggerInvestigation(txnId, userId ?? null, "manual");
        setInvestigations((prev) => ({ ...prev, [txnId]: value || null }));
      } catch {
        try {
          const value = await getInvestigation(txnId);
          setInvestigations((prev) => ({ ...prev, [txnId]: value || null }));
        } catch {
          setInvestigations((prev) => ({ ...prev, [txnId]: null }));
        }
      }
    },
    [userId]
  );

  const filtered = useMemo(() => {
    if (severityFilter === "ALL") return rows;
    return rows.filter((r) => getSeverityKey(r) === severityFilter);
  }, [rows, severityFilter]);

  const stats = useMemo(() => {
    if (realStats && typeof realStats.total_reports === "number") {
      return {
        total_reports: realStats.total_reports,
        confirmed_fraud: realStats.confirmed_fraud ?? 0,
        accuracy_delta: realStats.accuracy_delta ?? 0,
      };
    }
    return { total_reports: rows.length, confirmed_fraud: 0, accuracy_delta: 0 };
  }, [realStats, rows.length]);

  const actionable = (row) =>
    row.userAction === "PENDING" || queuePending(row);

  const persistFraudShield = async (row, action) => {
    if (row.alertId != null) {
      await postFraudShieldAlertAction(userId, row.alertId, action);
    } else if (row.transactionId != null) {
      await postFraudShieldAlertActionByTransaction(userId, row.transactionId, action);
    }
  };

  const handleSafe = async (row) => {
    setActingKey(row.key);
    try {
      if (queuePending(row) && row.queueId) {
        await selfResolveReviewQueue(row.queueId, { resolution: "legitimate", notes: "" });
      }
      if (row.alertId != null || row.transactionId != null) {
        await persistFraudShield(row, "ALLOWED");
      }
      await load();
      onAlertsChanged?.();
      showToast("Marked as safe.", "success");
    } catch (e) {
      showToast(e.message || "Action failed", "error");
    } finally {
      setActingKey(null);
    }
  };

  const handleReportFraud = async (row) => {
    setActingKey(row.key);
    try {
      if (queuePending(row) && row.queueId) {
        await selfResolveReviewQueue(row.queueId, { resolution: "fraud", notes: "Reported from FraudShield" });
      }
      if (row.alertId != null || row.transactionId != null) {
        await persistFraudShield(row, "REPORTED");
      }
      await load();
      onAlertsChanged?.();
      showToast("Fraud reported — also file on National Cyber Crime Portal if needed.", "success");
    } catch (e) {
      showToast(e.message || "Action failed", "error");
    } finally {
      setActingKey(null);
    }
  };

  const handleDismiss = async (row) => {
    setActingKey(row.key);
    try {
      if (queuePending(row) && row.queueId) {
        await selfResolveReviewQueue(row.queueId, { resolution: "legitimate", notes: "Dismissed (FraudShield)" });
      }
      if ((row.alertId != null || row.transactionId != null) && row.userAction === "PENDING") {
        await persistFraudShield(row, "ALLOWED");
      }
      await load();
      onAlertsChanged?.();
      showToast("Dismissed.", "success");
    } catch (e) {
      showToast(e.message || "Action failed", "error");
    } finally {
      setActingKey(null);
    }
  };

  const drawerItem = drawerRow
    ? {
        id: drawerRow.queueId,
        transaction_id: drawerRow.transactionId,
        merchant: drawerRow.merchant,
        description: drawerRow.pattern,
        amount: drawerRow.amount,
        severity: drawerRow.severity,
        risk_score: drawerRow.riskScore,
        status: drawerRow.queueStatus,
        notes: drawerRow.notes,
        created_at: drawerRow.date,
        payment_method: drawerRow.paymentMethod,
      }
    : null;

  if (loading && !rows.length) {
    return (
      <div className="space-y-3 p-1">
        <p className="text-xs text-white/40 mb-3">Loading unified alerts…</p>
        <SkeletonCard lines={4} height={160} />
      </div>
    );
  }

  if (error && !rows.length) {
    return <ErrorCard message={error} onRetry={load} />;
  }

  return (
    <>
      <div className="max-w-4xl mx-auto space-y-6 pb-8">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex flex-wrap items-start justify-between gap-4"
        >
          <div>
            <h2 className="text-2xl font-bold text-white flex items-center gap-2">
              <Inbox size={22} className="text-orange-400" />
              Alerts
            </h2>
            <p className="text-gray-400 text-sm mt-1">
              FraudShield scored alerts and Phase 8 review queue — one list, scoped to your dashboard view.
            </p>
          </div>
          <button
            type="button"
            onClick={() => load()}
            className="flex items-center gap-1.5 text-xs px-3 py-2 rounded-lg bg-white/10 text-gray-300 hover:bg-white/15 transition font-medium"
          >
            <RefreshCw size={13} />
            Refresh
          </button>
        </motion.div>

        <div className="grid grid-cols-3 gap-3">
          {[
            { label: "Signals in view", value: stats.total_reports ?? 0, color: "#3b82f6" },
            { label: "Confirmed fraud", value: stats.confirmed_fraud ?? 0, color: "#ef4444" },
            {
              label: "Model improvement",
              value: stats.accuracy_delta ? `+${(stats.accuracy_delta * 100).toFixed(1)}%` : "—",
              color: "#10b981",
            },
          ].map(({ label, value, color }) => (
            <div
              key={label}
              className="rounded-xl border border-white/[0.08] bg-white/[0.04] p-4 text-center shadow-[0_8px_32px_-16px_rgba(0,0,0,0.6)]"
            >
              <p className="text-2xl font-bold" style={{ color }}>
                {value}
              </p>
              <p className="text-xs text-white/45 mt-0.5">{label}</p>
            </div>
          ))}
        </div>

        <div className="flex flex-wrap gap-2 items-center">
          {SEVERITY_FILTERS.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setSeverityFilter(s)}
              className={`px-3 py-1 rounded-full text-sm font-medium border transition-all ${
                severityFilter === s
                  ? "bg-red-600 text-white border-red-600"
                  : "bg-transparent text-gray-400 border-gray-600 hover:border-red-400 hover:text-red-300"
              }`}
            >
              {s}
            </button>
          ))}
          {severityFilter !== "ALL" ? (
            <span className="text-xs text-gray-500">
              — {filtered.length} alert{filtered.length !== 1 ? "s" : ""}
            </span>
          ) : null}
        </div>

        <div className="flex flex-wrap gap-3 text-[11px]">
          <a
            href="https://cybercrime.gov.in"
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1 text-violet-400 hover:text-violet-300"
          >
            <ExternalLink size={11} />
            cybercrime.gov.in
          </a>
          <span className="flex items-center gap-1 font-bold text-white/70">
            <Phone size={10} />
            1930
          </span>
        </div>

        {!filtered.length ? (
          <div className="flex flex-col items-center gap-3 py-12 rounded-2xl border border-white/[0.06] bg-white/[0.02]">
            <ShieldCheck size={40} className="text-emerald-500/50" />
            <p className="font-medium text-white/60">No alerts in this view</p>
            <p className="text-xs text-white/35 text-center max-w-sm">
              Nothing matched your filters. Try ALL, or upload transactions and run a fraud check from Overview.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            <AnimatePresence>
              {filtered.map((row) => {
                const sev = getSeverityKey(row);
                const colors = SEVERITY_COLORS[sev] || SEVERITY_COLORS.LOW;
                const inv = row.transactionId ? investigations[row.transactionId] : undefined;
                const invLabel = investigationStatusLabel(row, inv);
                const conf =
                  inv && typeof inv.confidence === "number" && !inv.skipped
                    ? `${Math.round(inv.confidence <= 1 ? inv.confidence * 100 : inv.confidence)}%`
                    : null;
                const acting = actingKey === row.key;

                return (
                  <motion.article
                    key={row.key}
                    layout
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, x: -12 }}
                    role="button"
                    tabIndex={0}
                    onClick={() => setDrawerRow(row)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        setDrawerRow(row);
                      }
                    }}
                    className="rounded-2xl border border-white/[0.08] bg-white/[0.04] p-4 text-left cursor-pointer hover:border-violet-400/35 transition"
                  >
                    <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <ShieldAlert size={16} className="text-red-400 shrink-0" />
                          <h3 className="font-semibold text-white truncate">{row.merchant}</h3>
                          <span
                            className={`text-[10px] px-2 py-0.5 rounded-full font-bold border shrink-0 ${colors.bg} ${colors.text} ${colors.border}`}
                          >
                            {fraudAlertDisplayLabel(row.alertType || row.pattern, row.riskScore)}
                          </span>
                          <span className="text-[10px] text-white/40 uppercase tracking-wide shrink-0">
                            {row.sourceLabel}
                          </span>
                        </div>
                        <p className="text-xs text-white/50 mt-1 tabular-nums">
                          {row.transactionId ? `#${row.transactionId} · ` : ""}
                          {fmtCurrency(row.amount)}
                          {row.date ? ` · ${fmtRelativeTime(row.date)}` : ""}
                          {row.paymentMethod ? ` · ${row.paymentMethod}` : ""}
                        </p>
                        {row.pattern ? (
                          <p className="text-xs text-white/55 mt-2 line-clamp-2">{row.pattern}</p>
                        ) : null}
                        {row.hinglish ? (
                          <p className="text-[11px] text-white/45 mt-1 italic line-clamp-2">{row.hinglish}</p>
                        ) : null}
                        <div className="flex flex-wrap gap-2 mt-2 text-[10px]">
                          {invLabel ? (
                            <span className="px-2 py-0.5 rounded-full bg-white/[0.06] border border-white/10 text-white/70">
                              Review: {invLabel}
                            </span>
                          ) : null}
                          {conf ? (
                            <span className="px-2 py-0.5 rounded-full bg-violet-500/15 border border-violet-500/30 text-violet-200">
                              Investigation confidence {conf}
                            </span>
                          ) : null}
                          {!queuePending(row) && row.userAction !== "PENDING" ? (
                            <span className="px-2 py-0.5 rounded-full bg-slate-500/20 text-slate-300 border border-slate-500/30">
                              Action: {row.userAction}
                            </span>
                          ) : null}
                        </div>
                    </div>

                    {actionable(row) ? (
                      <div
                        className="mt-4 grid grid-cols-1 sm:grid-cols-3 gap-2"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <button
                          type="button"
                          disabled={acting}
                          onClick={() => handleSafe(row)}
                          className="flex items-center justify-center gap-2 py-2.5 rounded-xl bg-emerald-500/10 border border-emerald-500/25 text-emerald-300 text-xs font-semibold hover:bg-emerald-500/20 disabled:opacity-50"
                        >
                          {acting ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={14} />}
                          It was safe
                        </button>
                        <button
                          type="button"
                          disabled={acting}
                          onClick={() => handleReportFraud(row)}
                          className="flex items-center justify-center gap-2 py-2.5 rounded-xl bg-red-500/15 border border-red-500/35 text-red-300 text-xs font-semibold hover:bg-red-500/25 disabled:opacity-50"
                        >
                          {acting ? <Loader2 size={14} className="animate-spin" /> : <Flag size={14} />}
                          Report fraud
                        </button>
                        <button
                          type="button"
                          disabled={acting}
                          onClick={() => handleDismiss(row)}
                          className="flex items-center justify-center gap-2 py-2.5 rounded-xl bg-white/[0.05] border border-white/10 text-white/60 text-xs font-semibold hover:bg-white/[0.08] disabled:opacity-50"
                        >
                          Dismiss
                        </button>
                      </div>
                    ) : null}
                  </motion.article>
                );
              })}
            </AnimatePresence>
          </div>
        )}
      </div>

      <AlertDrawer
        item={drawerItem}
        onClose={() => setDrawerRow(null)}
        investigationState={
          drawerRow?.transactionId ? investigations[drawerRow.transactionId] : undefined
        }
        onRefreshInv={refreshOneInvestigation}
        onTriggerInv={triggerOneInvestigation}
      />
    </>
  );
};

export default UnifiedFraudAlerts;
