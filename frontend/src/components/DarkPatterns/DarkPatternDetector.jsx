import React, { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertTriangle,
  Award,
  Calendar,
  CheckCircle2,
  Clock,
  Copy,
  DollarSign,
  ExternalLink,
  LayoutGrid,
  RefreshCw,
  Shield,
  Sparkles,
  TrendingUp,
  Zap,
} from "lucide-react";
import {
  actionPatternAlert,
  apiUtils,
  dismissPatternAlert,
  downloadPatternAlertCalendarBlob,
  generatePatternAlerts,
  getDarkPatterns,
  getPatternAlertSavings,
  getPatternAlertsActive,
  getRupeeTraps,
  resolveDarkPattern,
  scanDarkPatterns,
  snoozePatternAlert,
} from "../../services/api";
import { useToast } from "../common/Toast";
import { EmptyState } from "../common/EmptyState";
import { ErrorCard } from "../common/ErrorCard";
import { PageHeader } from "../Dashboard/shared/PageHeader";
import { HeroKpiTile } from "../Dashboard/shared/HeroKpiTile";
import { inr } from "../../lib/format";

const ACCENT = "#10B981";

function formatCompactINR(amount) {
  const x = Number(amount || 0);
  if (x >= 10000000) return `₹${(x / 10000000).toFixed(1)}Cr`;
  if (x >= 100000) return `₹${(x / 100000).toFixed(1)}L`;
  if (x >= 1000) return `₹${Math.round(x / 1000)}K`;
  return apiUtils.formatINR(x);
}

function patternTypeIcon(patternType) {
  switch (patternType) {
    case "DUPLICATE_CHARGE":
      return "⚠️";
    case "FREE_TRIAL_TRAP":
      return "🎯";
    case "PRICE_INCREASE":
      return "📈";
    case "ESCALATING":
      return "📊";
    case "ZOMBIE":
      return "🧟";
    case "EK_RUPEE_TRAP":
      return "💀";
    default:
      return "🔎";
  }
}

function severityDotClass(sev) {
  if (sev === "CRITICAL") return "bg-red-500 shadow-red-500/50";
  if (sev === "HIGH") return "bg-orange-500 shadow-orange-500/40";
  if (sev === "MEDIUM") return "bg-amber-400 shadow-amber-400/40";
  return "bg-emerald-500 shadow-emerald-500/35";
}

function severityRowShell(sev) {
  if (sev === "CRITICAL")
    return "border-red-500/45 bg-gradient-to-br from-red-500/15 to-red-500/5 hover:border-red-500/65";
  if (sev === "HIGH")
    return "border-orange-500/40 bg-gradient-to-br from-orange-500/14 to-orange-500/5 hover:border-orange-500/60";
  if (sev === "MEDIUM")
    return "border-amber-400/35 bg-gradient-to-br from-amber-400/12 to-amber-500/5 hover:border-amber-400/55";
  return "border-emerald-500/30 bg-gradient-to-br from-emerald-500/10 to-exiqo-dark/40 hover:border-emerald-400/50";
}

function detailCardShell(sev) {
  if (sev === "CRITICAL")
    return "border-2 border-red-500/45 bg-gradient-to-br from-red-500/18 via-exiqo-dark/90 to-red-500/8";
  if (sev === "HIGH")
    return "border-2 border-orange-500/40 bg-gradient-to-br from-orange-500/15 via-exiqo-dark/90 to-orange-500/8";
  if (sev === "MEDIUM")
    return "border-2 border-amber-400/35 bg-gradient-to-br from-amber-400/12 via-exiqo-dark/90 to-amber-500/6";
  return "border-2 border-emerald-500/30 bg-gradient-to-br from-emerald-500/12 via-exiqo-dark/90 to-exiqo-purple/8";
}

function severityChipClass(sev) {
  if (sev === "CRITICAL") return "border border-red-500/50 bg-red-500/30 text-red-200";
  if (sev === "HIGH") return "border border-orange-500/45 bg-orange-500/25 text-orange-100";
  if (sev === "MEDIUM") return "border border-amber-500/40 bg-amber-500/20 text-amber-100";
  return "border border-emerald-500/35 bg-emerald-500/20 text-emerald-100";
}

const DarkPatternDetector = ({ userId }) => {
  const { showToast } = useToast();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [patternsData, setPatternsData] = useState(null);
  const [rupeeData, setRupeeData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [copiedId, setCopiedId] = useState(null);
  const [selectedKey, setSelectedKey] = useState(null);
  const [proactive, setProactive] = useState(null);
  const [proactiveSavings, setProactiveSavings] = useState(null);
  const [proactiveLoading, setProactiveLoading] = useState(false);
  const [proactiveBusy, setProactiveBusy] = useState(false);

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const [patterns, rupee] = await Promise.all([getDarkPatterns(userId), getRupeeTraps(userId)]);
      setPatternsData(patterns);
      setRupeeData(rupee);
    } catch (err) {
      setError(err.message || "Unable to load dark pattern report");
    } finally {
      setLoading(false);
    }
  };

  const loadProactive = async () => {
    if (!userId) return;
    setProactiveLoading(true);
    try {
      const [active, savings] = await Promise.all([
        getPatternAlertsActive(userId),
        getPatternAlertSavings(userId),
      ]);
      setProactive(active);
      setProactiveSavings(savings);
    } catch {
      setProactive(null);
      setProactiveSavings(null);
    } finally {
      setProactiveLoading(false);
    }
  };

  const runProactiveScan = async () => {
    if (!userId) return;
    setProactiveBusy(true);
    try {
      await generatePatternAlerts(userId);
      showToast("Upcoming charges re-scanned from your transactions");
      await loadProactive();
    } catch (e) {
      showToast(e?.message || "Prediction scan failed");
    } finally {
      setProactiveBusy(false);
    }
  };

  useEffect(() => {
    load();
  }, [userId]);

  useEffect(() => {
    loadProactive();
  }, [userId]);

  useEffect(() => {
    const handler = () => { load(); loadProactive(); };
    window.addEventListener("dashboardModeChanged", handler);
    return () => window.removeEventListener("dashboardModeChanged", handler);
  }, [userId]);

  const strongestTrap = useMemo(() => {
    const traps = rupeeData?.traps || [];
    if (!traps.length) return null;
    return [...traps].sort((a, b) => (b.total_lost || 0) - (a.total_lost || 0))[0];
  }, [rupeeData]);

  const patterns = patternsData?.patterns || [];

  const timelineEvents = useMemo(() => {
    const ev = [];
    if (strongestTrap) {
      ev.push({
        key: "rupee",
        kind: "rupee",
        severity: "CRITICAL",
        title: "One-rupee trap",
        subtitle: strongestTrap.merchant,
        description: strongestTrap.warning || strongestTrap.english_explanation || "Escalating micro-debit pattern.",
        sortDate: strongestTrap.initial_date || "",
        icon: "💀",
        trap: strongestTrap,
      });
    }
    for (const p of patterns) {
      ev.push({
        key: `pattern-${p.id}`,
        kind: "pattern",
        severity: p.severity || "MEDIUM",
        title: (p.pattern_type || "").replaceAll("_", " "),
        subtitle: p.merchant,
        description: p.description,
        sortDate: p.detected_date || "",
        icon: patternTypeIcon(p.pattern_type),
        pattern: p,
      });
    }
    ev.sort((a, b) => {
      const da = Date.parse(a.sortDate) || 0;
      const db = Date.parse(b.sortDate) || 0;
      return db - da;
    });
    return ev;
  }, [strongestTrap, patterns]);

  useEffect(() => {
    if (!timelineEvents.length) {
      setSelectedKey(null);
      return;
    }
    setSelectedKey((prev) => {
      if (prev && timelineEvents.some((e) => e.key === prev)) return prev;
      return timelineEvents[0].key;
    });
  }, [timelineEvents]);

  const selectedEvent = useMemo(
    () => timelineEvents.find((e) => e.key === selectedKey) || null,
    [timelineEvents, selectedKey],
  );

  const totalThreats = patternsData?.total_dark_patterns ?? 0;
  const atRisk = patternsData?.total_money_at_risk || 0;
  const recoverable = patternsData?.potential_refunds || 0;
  const criticalCount = patternsData?.critical_count ?? 0;

  const protectionPct = useMemo(() => {
    if (!timelineEvents.length) return 100;
    const penalty = Math.min(40, criticalCount * 9 + Math.min(15, totalThreats * 2));
    return Math.max(58, Math.round(100 - penalty));
  }, [timelineEvents.length, criticalCount, totalThreats]);

  const onScan = async () => {
    setBusy(true);
    try {
      await scanDarkPatterns(userId);
      await load();
      await loadProactive();
    } finally {
      setBusy(false);
    }
  };

  const onResolve = async (patternId) => {
    setBusy(true);
    try {
      await resolveDarkPattern(userId, patternId);
      await load();
      showToast("Charge marked as resolved ✅");
    } finally {
      setBusy(false);
    }
  };

  const copyEvidence = async (payload, copyKey) => {
    try {
      const text = JSON.stringify(payload || {}, null, 2);
      await navigator.clipboard.writeText(text);
      setCopiedId(copyKey);
      setTimeout(() => setCopiedId(null), 2000);
      showToast("Evidence copied to clipboard");
    } catch {
      showToast("Could not copy — try again");
    }
  };

  const onProactiveSnooze = async (alertId) => {
    setProactiveBusy(true);
    try {
      await snoozePatternAlert(userId, { alert_id: alertId, snooze_hours: 24 });
      showToast("Reminder snoozed for 24 hours");
      await loadProactive();
    } catch (e) {
      showToast(e?.message || "Snooze failed");
    } finally {
      setProactiveBusy(false);
    }
  };

  const onProactiveDismiss = async (alertId) => {
    setProactiveBusy(true);
    try {
      await dismissPatternAlert(userId, { alert_id: alertId, reason: "dismissed_in_app" });
      await loadProactive();
    } catch (e) {
      showToast(e?.message || "Dismiss failed");
    } finally {
      setProactiveBusy(false);
    }
  };

  const onProactiveCancelled = async (alertId) => {
    setProactiveBusy(true);
    try {
      const r = await actionPatternAlert(userId, { alert_id: alertId, action: "cancelled", notes: "" });
      const saved = Number(r?.savings_added || 0);
      showToast(saved > 0 ? `Logged cancel — tracked ${inr(saved)}` : "Action saved");
      await loadProactive();
    } catch (e) {
      showToast(e?.message || "Action failed");
    } finally {
      setProactiveBusy(false);
    }
  };

  const onDownloadIcs = async (alertId) => {
    try {
      const blob = await downloadPatternAlertCalendarBlob(userId, alertId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `smartspend_alert_${alertId}.ics`;
      a.click();
      URL.revokeObjectURL(url);
      showToast("Calendar file downloaded");
    } catch (e) {
      showToast(e?.message || "Download failed");
    }
  };

  if (loading) {
    return (
      <div className="mx-auto max-w-6xl space-y-6">
        <div className="h-48 animate-pulse rounded-3xl bg-exiqo-dark/40" />
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="h-80 animate-pulse rounded-2xl bg-exiqo-dark/35" />
          <div className="h-80 animate-pulse rounded-2xl bg-exiqo-dark/35" />
        </div>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-28 animate-pulse rounded-xl bg-exiqo-dark/30" />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="mx-auto max-w-6xl rounded-2xl border border-exiqo-purple/20 bg-exiqo-dark/40 p-6">
        <ErrorCard message={error} onRetry={load} />
      </div>
    );
  }

  const showReportLink =
    selectedEvent?.kind === "rupee" || selectedEvent?.severity === "CRITICAL";

  const totalDetected = (patternsData?.patterns?.length || 0) + (rupeeData?.traps?.length || 0);
  const totalLost     = (rupeeData?.traps || []).reduce((s, t) => s + Number(t.total_lost || 0), 0);

  return (
    <div className="mx-auto max-w-6xl space-y-6 pb-6">
      <PageHeader
        eyebrow="ANALYTICS"
        title="Growth Lens"
        subtitle="AI detects dark billing patterns, duplicate charges, and escalating ₹1 traps in your transactions."
        accentHex={ACCENT}
        rightSlot={
          <HeroKpiTile
            label="Patterns detected"
            value={String(totalDetected)}
            caption={totalLost ? `${inr(totalLost)} lost to rupee traps` : "Monitoring your transactions"}
            accentHex={ACCENT}
            loading={loading}
          />
        }
      />

      {/* Action strip */}
      <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="inline-flex items-center gap-2 rounded-xl border-2 border-green-500/45 bg-green-500/15 px-3 py-2">
              <Zap className="h-5 w-5 shrink-0 text-green-400" />
              <span className="text-sm font-bold text-green-300">Live analysis</span>
            </div>
            <button
              type="button"
              onClick={onScan}
              disabled={busy}
              className="inline-flex items-center justify-center gap-2 rounded-xl bg-exiqo-purple px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-exiqo-purple/35 transition hover:bg-exiqo-purple/90 disabled:opacity-50"
            >
              <RefreshCw className={`h-4 w-4 ${busy ? "animate-spin" : ""}`} />
              {busy ? "Scanning…" : "Run fresh scan"}
            </button>
      </div>

      <section className="rounded-3xl border border-cyan-500/25 bg-gradient-to-br from-cyan-500/10 to-exiqo-dark/60 p-5">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-bold text-white">Upcoming charge alerts</h2>
            <p className="mt-1 max-w-2xl text-sm text-gray-400">
              Predicted from your real debits (trials, renewals, ₹1 verification follow-ups). Snooze, dismiss, or add a
              calendar reminder before the charge date.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={runProactiveScan}
              disabled={proactiveBusy || proactiveLoading}
              className="inline-flex items-center gap-2 rounded-xl border border-cyan-400/40 bg-cyan-500/15 px-4 py-2 text-sm font-semibold text-cyan-100 transition hover:bg-cyan-500/25 disabled:opacity-50"
            >
              <Zap className="h-4 w-4" />
              {proactiveBusy ? "Scanning…" : "Predict & refresh"}
            </button>
            <button
              type="button"
              onClick={loadProactive}
              disabled={proactiveLoading}
              className="rounded-xl border border-white/15 bg-white/[0.06] px-4 py-2 text-sm font-medium text-white/90 hover:bg-white/10 disabled:opacity-50"
            >
              Reload
            </button>
          </div>
        </div>
        {proactiveSavings?.savings?.this_month ? (
          <div className="mb-4 grid gap-2 sm:grid-cols-3">
            <div className="rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-sm">
              <p className="text-gray-500">Prevented (month)</p>
              <p className="font-semibold text-emerald-300">
                {inr(proactiveSavings.savings.this_month.amount_saved || 0)}
              </p>
            </div>
            <div className="rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-sm">
              <p className="text-gray-500">Count (month)</p>
              <p className="font-semibold text-white">{proactiveSavings.savings.this_month.patterns_prevented || 0}</p>
            </div>
            <div className="rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-sm">
              <p className="text-gray-500">All-time saved</p>
              <p className="font-semibold text-cyan-200">
                {inr(proactiveSavings.savings.all_time?.amount_saved || 0)}
              </p>
            </div>
          </div>
        ) : null}
        {proactiveLoading ? (
          <p className="text-sm text-gray-400">Loading proactive alerts…</p>
        ) : !proactive?.counts?.total ? (
          <p className="text-sm text-gray-400">
            No upcoming alerts right now. Run <strong>Predict & refresh</strong> after migrations are applied, or when you
            have new subscription-like debits.
          </p>
        ) : (
          <div className="space-y-4">
            {[
              ["critical", "Act now", AlertTriangle, "border-red-500/40 bg-red-500/10"],
              ["urgent", "Next 3 days", Clock, "border-orange-500/35 bg-orange-500/10"],
              ["upcoming", "Later", Calendar, "border-emerald-500/30 bg-emerald-500/8"],
            ].map(([key, label, Icon, shell]) => {
              const list = proactive?.alerts?.[key] || [];
              if (!list.length) return null;
              return (
                <div key={key} className={`rounded-2xl border p-4 ${shell}`}>
                  <div className="mb-3 flex items-center gap-2">
                    <Icon className="h-4 w-4 text-white/80" />
                    <h3 className="text-sm font-bold uppercase tracking-wide text-white/90">{label}</h3>
                    <span className="text-xs text-gray-400">({list.length})</span>
                  </div>
                  <ul className="space-y-3">
                    {list.map((a) => (
                      <li
                        key={a.id}
                        className="flex flex-col gap-2 rounded-xl border border-white/10 bg-exiqo-dark/50 p-3 sm:flex-row sm:items-center sm:justify-between"
                      >
                        <div>
                          <p className="font-semibold text-white">{a.merchant_name}</p>
                          <p className="text-xs text-gray-400">
                            {(a.pattern_type || "").replaceAll("_", " ")} · {inr(a.charge_amount)} on{" "}
                            {a.charge_date ? new Date(a.charge_date).toLocaleDateString("en-IN") : "—"} ·{" "}
                            <span className="text-amber-200/90">{a.days_until_charge}d left</span>
                          </p>
                          {a.cancellation_url ? (
                            <a
                              href={a.cancellation_url}
                              target="_blank"
                              rel="noreferrer"
                              className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-cyan-300 hover:underline"
                            >
                              Open cancel page <ExternalLink className="h-3 w-3" />
                            </a>
                          ) : null}
                        </div>
                        <div className="flex flex-wrap gap-2">
                          {a.cancellation_url ? (
                            <button
                              type="button"
                              disabled={proactiveBusy}
                              onClick={() => window.open(a.cancellation_url, "_blank", "noopener,noreferrer")}
                              className="rounded-lg border border-green-500/40 bg-green-500/15 px-3 py-1.5 text-xs font-semibold text-green-200 hover:bg-green-500/25 disabled:opacity-50"
                            >
                              Cancel now
                            </button>
                          ) : null}
                          <button
                            type="button"
                            disabled={proactiveBusy}
                            onClick={() => onDownloadIcs(a.id)}
                            className="inline-flex items-center gap-1 rounded-lg border border-white/15 bg-white/[0.06] px-3 py-1.5 text-xs font-medium text-white/85 hover:bg-white/10 disabled:opacity-50"
                          >
                            <Calendar className="h-3.5 w-3.5" /> .ics
                          </button>
                          <button
                            type="button"
                            disabled={proactiveBusy}
                            onClick={() => onProactiveSnooze(a.id)}
                            className="rounded-lg border border-white/15 px-3 py-1.5 text-xs text-gray-300 hover:bg-white/5 disabled:opacity-50"
                          >
                            Snooze 24h
                          </button>
                          <button
                            type="button"
                            disabled={proactiveBusy}
                            onClick={() => onProactiveCancelled(a.id)}
                            className="rounded-lg border border-emerald-500/35 bg-emerald-500/10 px-3 py-1.5 text-xs font-semibold text-emerald-200 disabled:opacity-50"
                          >
                            I cancelled
                          </button>
                          <button
                            type="button"
                            disabled={proactiveBusy}
                            onClick={() => onProactiveDismiss(a.id)}
                            className="rounded-lg px-3 py-1.5 text-xs text-gray-500 hover:text-white/70 disabled:opacity-50"
                          >
                            Dismiss
                          </button>
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })}
          </div>
        )}
      </section>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {[
              {
                label: "Threats found",
                value: String(totalThreats),
                icon: Sparkles,
                tile: "bg-red-500/25 text-red-300",
              },
              {
                label: "At risk",
                value: formatCompactINR(atRisk),
                icon: DollarSign,
                tile: "bg-orange-500/25 text-orange-300",
              },
              {
                label: "Recoverable",
                value: formatCompactINR(recoverable),
                icon: TrendingUp,
                tile: "bg-green-500/25 text-green-300",
              },
              {
                label: "Shield score",
                value: `${protectionPct}%`,
                icon: Award,
                tile: "bg-purple-500/25 text-purple-200",
              },
            ].map((s) => (
              <div
                key={s.label}
                className="rounded-xl border border-white/15 bg-white/10 p-4 shadow-inner backdrop-blur-md"
              >
                <div className="flex items-center gap-3">
                  <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${s.tile}`}>
                    <s.icon className="h-5 w-5" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-xs font-semibold uppercase tracking-wide text-white/60">{s.label}</p>
                    <p className="truncate text-xl font-bold tabular-nums text-white sm:text-2xl">{s.value}</p>
                  </div>
                </div>
              </div>
            ))}
      </div>

      {/* Timeline + detail */}
      <div className="rounded-2xl border-2 border-exiqo-purple/25 bg-exiqo-dark/55 p-4 backdrop-blur-xl sm:p-6">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-2">
          <h2 className="flex items-center gap-2 text-lg font-bold text-white sm:text-xl">
            <Clock className="h-6 w-6 shrink-0 text-exiqo-purple" />
            Fraud detection timeline
          </h2>
          <span className="text-sm text-gray-400">Recent signals (newest first)</span>
        </div>

        {!timelineEvents.length ? (
          <div className="rounded-xl border border-dashed border-exiqo-purple/30 bg-exiqo-dark/30 py-12">
            <EmptyState
              icon="✅"
              title="No timeline events yet"
              subtitle="No rupee-trap signal and no dark patterns in the current window. Run a scan after new transactions import."
            />
          </div>
        ) : (
          <div className="grid gap-6 lg:grid-cols-12 lg:gap-8">
            <div className="relative lg:col-span-5">
              <div className="pointer-events-none absolute bottom-4 left-[1.4rem] top-4 w-0.5 bg-gradient-to-b from-red-500 via-orange-500 to-emerald-500 opacity-90" />
              <ul className="relative space-y-4">
                {timelineEvents.map((ev, idx) => {
                  const active = selectedKey === ev.key;
                  return (
                    <motion.li
                      key={ev.key}
                      initial={{ opacity: 0, x: -12 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: Math.min(idx * 0.06, 0.25) }}
                      className="relative pl-14"
                    >
                      <div
                        className={`absolute left-[0.55rem] top-3 flex h-7 w-7 items-center justify-center rounded-full border-4 border-exiqo-navy ${severityDotClass(
                          ev.severity,
                        )}`}
                        aria-hidden
                      >
                        <span className="text-[10px] leading-none">{ev.icon}</span>
                      </div>
                      <button
                        type="button"
                        onClick={() => setSelectedKey(ev.key)}
                        className={`w-full rounded-xl border-2 p-4 text-left transition-all ${severityRowShell(
                          ev.severity,
                        )} ${active ? "ring-2 ring-exiqo-purple ring-offset-2 ring-offset-exiqo-navy" : ""}`}
                      >
                        <div className="mb-1 flex flex-wrap items-center gap-2">
                          <span
                            className={`rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${severityChipClass(
                              ev.severity,
                            )}`}
                          >
                            {ev.severity}
                          </span>
                          <span className="text-sm font-bold capitalize text-white">{ev.title}</span>
                        </div>
                        <p className="truncate text-xs font-semibold text-white/85">{ev.subtitle}</p>
                        <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-gray-400">{ev.description}</p>
                        {ev.sortDate ? (
                          <p className="mt-2 text-[11px] font-medium uppercase tracking-wider text-gray-500">
                            {ev.sortDate}
                          </p>
                        ) : null}
                      </button>
                    </motion.li>
                  );
                })}
              </ul>
            </div>

            <div className="lg:col-span-7">
              <AnimatePresence mode="wait">
                {selectedEvent ? (
                  <motion.div
                    key={selectedEvent.key}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -6 }}
                    transition={{ duration: 0.2 }}
                    className={`relative overflow-hidden rounded-2xl p-5 sm:p-6 ${detailCardShell(selectedEvent.severity)}`}
                  >
                    <div className="pointer-events-none absolute -right-16 -top-16 h-48 w-48 rounded-full bg-red-500/10 blur-3xl" />
                    <div className="relative z-10">
                      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <div className="mb-2 flex flex-wrap items-center gap-2">
                            <span className="text-2xl" aria-hidden>
                              {selectedEvent.icon}
                            </span>
                            <span
                              className={`rounded-full px-3 py-1 text-xs font-bold uppercase ${severityChipClass(
                                selectedEvent.severity,
                              )}`}
                            >
                              {selectedEvent.severity}
                            </span>
                          </div>
                          <h3 className="text-lg font-bold capitalize text-white sm:text-xl">{selectedEvent.title}</h3>
                          <p className="mt-1 text-sm font-semibold text-gray-300">{selectedEvent.subtitle}</p>
                        </div>
                      </div>

                      <p className="mb-5 text-sm leading-relaxed text-white/90">{selectedEvent.description}</p>

                      {selectedEvent.kind === "rupee" && selectedEvent.trap ? (
                        <div className="mb-5 space-y-3">
                          <p className="text-sm text-white/90">
                            Initial debit{" "}
                            <span className="font-bold text-red-300">
                              {apiUtils.formatINR(selectedEvent.trap.initial_amount)}
                            </span>
                            {selectedEvent.trap.total_lost != null ? (
                              <>
                                {" "}
                                · Total flagged{" "}
                                <span className="font-bold text-orange-300">
                                  {apiUtils.formatINR(selectedEvent.trap.total_lost)}
                                </span>
                              </>
                            ) : null}
                          </p>
                          {(selectedEvent.trap.escalation_amounts || []).length > 0 ? (
                            <div className="flex flex-wrap gap-2">
                              {(selectedEvent.trap.escalation_amounts || []).map((a, i) => (
                                <span
                                  key={`${a}-${i}`}
                                  className="rounded-lg border border-red-500/45 bg-red-500/25 px-3 py-1.5 text-sm font-bold text-red-100"
                                >
                                  {apiUtils.formatINR(a)}
                                </span>
                              ))}
                            </div>
                          ) : null}
                          {selectedEvent.trap.english_explanation ? (
                            <p className="text-sm text-gray-400">{selectedEvent.trap.english_explanation}</p>
                          ) : null}
                        </div>
                      ) : null}

                      {selectedEvent.kind === "pattern" && selectedEvent.pattern ? (
                        <div className="mb-5 grid gap-4 border-y border-white/10 py-4 sm:grid-cols-3">
                          <div>
                            <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-500">
                              Amount involved
                            </p>
                            <p className="text-lg font-bold tabular-nums text-white">
                              {apiUtils.formatINR(selectedEvent.pattern.amount_involved || 0)}
                            </p>
                          </div>
                          <div>
                            <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-500">
                              Refund possible
                            </p>
                            <p className="text-lg font-bold tabular-nums text-green-400">
                              {selectedEvent.pattern.refund_amount
                                ? apiUtils.formatINR(selectedEvent.pattern.refund_amount)
                                : "—"}
                            </p>
                          </div>
                          <div className="sm:col-span-1">
                            <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-500">
                              Next step
                            </p>
                            <p className="text-sm font-semibold leading-snug text-orange-300">
                              {selectedEvent.pattern.action}
                            </p>
                          </div>
                        </div>
                      ) : null}

                      <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap">
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => {
                            if (selectedEvent.kind === "pattern" && selectedEvent.pattern) {
                              copyEvidence(selectedEvent.pattern.evidence, `pattern-${selectedEvent.pattern.id}`);
                            } else if (selectedEvent.kind === "rupee" && selectedEvent.trap) {
                              copyEvidence(selectedEvent.trap, "rupee");
                            }
                          }}
                          className="inline-flex flex-1 items-center justify-center gap-2 rounded-lg border border-exiqo-purple/45 bg-exiqo-dark/60 px-4 py-2.5 text-sm font-semibold text-gray-300 transition hover:bg-exiqo-purple/20 hover:text-white disabled:opacity-50 sm:flex-initial sm:min-w-[140px]"
                        >
                          {copiedId ===
                          (selectedEvent.kind === "pattern" && selectedEvent.pattern
                            ? `pattern-${selectedEvent.pattern.id}`
                            : "rupee") ? (
                            <>
                              <CheckCircle2 className="h-4 w-4 text-green-400" />
                              Copied
                            </>
                          ) : (
                            <>
                              <Copy className="h-4 w-4" />
                              Copy evidence
                            </>
                          )}
                        </button>

                        {showReportLink ? (
                          <a
                            href="https://cybercrime.gov.in"
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex flex-1 items-center justify-center gap-2 rounded-lg border border-orange-500/45 bg-orange-500/15 px-4 py-2.5 text-sm font-semibold text-orange-300 transition hover:bg-orange-500/25 sm:flex-initial sm:min-w-[140px]"
                          >
                            Report fraud
                            <ExternalLink className="h-4 w-4 shrink-0" />
                          </a>
                        ) : null}

                        {selectedEvent.kind === "pattern" && selectedEvent.pattern ? (
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => onResolve(selectedEvent.pattern.id)}
                            className="inline-flex flex-1 items-center justify-center rounded-lg border border-green-500/45 bg-green-500/15 px-4 py-2.5 text-sm font-semibold text-green-300 transition hover:bg-green-500/25 disabled:opacity-50 sm:flex-initial sm:min-w-[140px]"
                          >
                            Mark resolved
                          </button>
                        ) : null}
                      </div>
                    </div>
                  </motion.div>
                ) : null}
              </AnimatePresence>
            </div>
          </div>
        )}
      </div>

      {/* Pattern grid */}
      {patterns.length > 0 ? (
        <div>
          <div className="mb-4 flex items-center gap-2">
            <LayoutGrid className="h-5 w-5 text-exiqo-purple" />
            <h2 className="text-lg font-bold text-white">All patterns</h2>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {patterns.map((p) => {
              const key = `pattern-${p.id}`;
              const active = selectedKey === key;
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => setSelectedKey(key)}
                  className={`rounded-2xl border-2 p-5 text-left transition-all ${severityRowShell(p.severity)} ${
                    active ? "ring-2 ring-exiqo-purple ring-offset-2 ring-offset-exiqo-navy" : ""
                  }`}
                >
                  <div className="mb-3 flex items-center justify-between gap-2">
                    <span className="text-2xl">{patternTypeIcon(p.pattern_type)}</span>
                    <span className={`rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase ${severityChipClass(p.severity)}`}>
                      {p.severity}
                    </span>
                  </div>
                  <p className="mb-1 text-xs font-bold uppercase tracking-wide text-gray-500">
                    {(p.pattern_type || "").replaceAll("_", " ")}
                  </p>
                  <p className="mb-2 line-clamp-2 text-base font-bold text-white">{p.merchant}</p>
                  <p className="line-clamp-2 text-xs leading-relaxed text-gray-400">{p.description}</p>
                  <div className="mt-4 flex items-center justify-between border-t border-white/10 pt-3 text-sm">
                    <span className="font-bold tabular-nums text-red-200">{apiUtils.formatINR(p.amount_involved || 0)}</span>
                    {p.refund_amount ? (
                      <span className="text-xs font-semibold text-green-400">
                        Up to {apiUtils.formatINR(p.refund_amount)}
                      </span>
                    ) : (
                      <span className="text-xs text-gray-500">Review</span>
                    )}
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      ) : strongestTrap ? null : (
        <div className="rounded-2xl border border-dashed border-exiqo-purple/25 bg-exiqo-dark/30 py-12">
          <EmptyState
            icon="🎉"
            title="No suspicious charges detected"
            subtitle="We did not find dark-pattern billing signals in your recent data. Stay alert on free trials and renewals."
          />
        </div>
      )}

      {/* Gamification / savings */}
      <div className="relative overflow-hidden rounded-2xl border-2 border-green-500/40 bg-gradient-to-br from-green-500/18 to-emerald-600/10 p-6">
        <div className="pointer-events-none absolute -bottom-10 right-0 h-40 w-40 rounded-full bg-emerald-400/15 blur-3xl" />
        <div className="relative z-10 flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-start gap-4">
            <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-green-500 to-emerald-600 shadow-xl shadow-green-500/30">
              <CheckCircle2 className="h-8 w-8 text-white" strokeWidth={2.2} />
            </div>
            <div>
              <h3 className="mb-1 text-xl font-bold text-white">Money you can fight for</h3>
              <p className="max-w-xl text-sm leading-relaxed text-green-100/80">
                {totalThreats > 0
                  ? `We surfaced ${totalThreats} pattern${totalThreats === 1 ? "" : "s"} — prioritize critical items, then duplicate charges.`
                  : "No active billing traps in this window. Keep scanning after large spends or new subscriptions."}
              </p>
              {patternsData?.ai_advice ? (
                <p className="mt-3 border-t border-white/15 pt-3 text-sm leading-relaxed text-green-50/75">
                  {patternsData.ai_advice}
                </p>
              ) : null}
            </div>
          </div>
          <div className="text-left lg:text-right">
            <p className="text-sm font-medium text-green-200/80">Recoverable (est.)</p>
            <p className="text-3xl font-bold tabular-nums text-white sm:text-4xl">{apiUtils.formatINR(recoverable)}</p>
            <p className="mt-1 text-xs text-green-200/65">Based on duplicate-charge refund signals in this report.</p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DarkPatternDetector;
