/**
 * BehaviorProfile — Phase 2 (Feature Store) deep-dive.
 * Shows: risk score, login patterns, location pattern map, typical pattern summary,
 * anomaly detection, and recent activity timeline.
 * `embedded` — FraudShield dark glass layout (no standalone page chrome).
 */

import React, { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  ArrowLeft,
  Activity,
  MapPin,
  Clock,
  AlertTriangle,
  User,
  Globe,
  Sparkles,
} from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { useViewMode } from "../../context/ViewModeContext";
import { getBehaviorProfile } from "../../services/riskApi";
import { RiskStatePlaceholder } from "../../components/risk/RiskStatePlaceholder";
import { fmtRelativeTime } from "../../utils/risk/formatters";
import { BehaviorRiskGauge } from "../../components/FraudShield/BehaviorRiskGauge";
import { LocationPatternMap } from "../../components/FraudShield/LocationPatternMap";

function formatHourLabel(h) {
  const hour = Number(h);
  const h12 = hour % 12 === 0 ? 12 : hour % 12;
  const suf = hour < 12 ? "am" : "pm";
  return `${h12}${suf}`;
}

function typicalWindow(login_patterns) {
  const peak = Math.max(0, ...(login_patterns || []).map((d) => d.count));
  if (peak === 0) return null;
  const thr = peak * 0.35;
  const active = (login_patterns || [])
    .filter((d) => d.count >= thr)
    .map((d) => parseInt(d.hour, 10))
    .filter((n) => !Number.isNaN(n));
  if (!active.length) return null;
  return { start: Math.min(...active), end: Math.max(...active) };
}

function anomalyHighlightHours(anomalies) {
  const set = new Set();
  for (const a of anomalies || []) {
    if (a.type === "unusual_hour" && a.description) {
      const m = a.description.match(/(\d{1,2}):(\d{2})\s*(AM|PM)/i);
      if (m) {
        let h = parseInt(m[1], 10);
        const ap = m[3].toUpperCase();
        if (ap === "PM" && h < 12) h += 12;
        if (ap === "AM" && h === 12) h = 0;
        set.add(String(h).padStart(2, "0"));
      }
    }
  }
  return set;
}

function TypicalPatternCard({ login_patterns, locations, embedded }) {
  const win = useMemo(() => typicalWindow(login_patterns), [login_patterns]);
  const cities = useMemo(() => {
    return [...(locations || [])].sort((a, b) => (b.count || 0) - (a.count || 0)).slice(0, 3);
  }, [locations]);

  const text = useMemo(() => {
    const parts = [];
    if (win) {
      parts.push(
        `You usually sign in between **${formatHourLabel(win.start)}** and **${formatHourLabel(win.end)}** (peak activity).`
      );
    }
    if (cities.length) {
      const names = cities.map((c) => c.city).join(", ");
      parts.push(`Most sessions originate from **${names}**.`);
    }
    if (!parts.length) return "Once we learn your cadence, we summarise it here so you can spot drift at a glance.";
    parts.push("Anything outside this pattern gets extra scrutiny in the decision engine.");
    return parts.join(" ");
  }, [win, cities]);

  const card = embedded
    ? "rounded-2xl border border-cyan-500/20 bg-gradient-to-br from-cyan-500/10 via-white/[0.04] to-violet-500/10 p-5 backdrop-blur-xl"
    : "rounded-2xl border border-indigo-100 bg-gradient-to-br from-indigo-50 to-white p-5 shadow-sm";

  const chunks = text.split(/\*\*(.*?)\*\*/g);

  return (
    <div className={card}>
      <div className="mb-2 flex items-center gap-2">
        <Sparkles className={embedded ? "h-4 w-4 text-cyan-300" : "h-4 w-4 text-indigo-500"} aria-hidden />
        <h3 className={embedded ? "text-sm font-bold text-white" : "text-sm font-bold text-gray-800"}>Your typical pattern</h3>
      </div>
      <p className={embedded ? "text-sm leading-relaxed text-gray-300" : "text-sm leading-relaxed text-gray-600"}>
        {chunks.map((chunk, i) =>
          i % 2 === 1 ? (
            <strong key={i} className={embedded ? "font-semibold text-white" : "font-semibold text-indigo-900"}>
              {chunk}
            </strong>
          ) : (
            <span key={i}>{chunk}</span>
          )
        )}
      </p>
    </div>
  );
}

function LoginPatternsChart({ data, embedded, highlightHours }) {
  const peak = Math.max(...data.map((d) => d.count));
  const wrap = embedded
    ? "rounded-2xl border border-white/10 bg-white/[0.03] p-5 backdrop-blur-xl"
    : "rounded-2xl border border-gray-100 bg-white p-5 shadow-sm";
  const title = embedded ? "text-sm font-semibold text-white" : "text-sm font-semibold text-gray-700";
  const sub = embedded ? "text-xs text-gray-500" : "text-xs text-gray-400";

  const barFill = (entry) => {
    const h = entry.hour;
    if (highlightHours?.has?.(h)) return "#fb7185";
    if (entry.count === peak && peak > 0) return "url(#barGradPeak)";
    if (entry.count > peak * 0.5 && peak > 0) return embedded ? "#a78bfa" : "#a78bfa";
    return embedded ? "rgba(255,255,255,0.12)" : "#e5e7eb";
  };

  return (
    <div className={wrap}>
      <h3 className={title}>Login patterns — hourly</h3>
      <p className={`${sub} mb-1`}>Activity frequency by hour · anomaly hours highlighted</p>
      <ResponsiveContainer width="100%" height={132}>
        <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -22 }}>
          <defs>
            <linearGradient id="barGradPeak" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#c4b5fd" />
              <stop offset="100%" stopColor="#7c3aed" />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="hour"
            tick={{ fontSize: 9, fill: embedded ? "rgba(226,232,240,0.45)" : "#9ca3af" }}
            tickLine={false}
            axisLine={false}
            interval={2}
          />
          <YAxis hide />
          <Tooltip
            cursor={{ fill: embedded ? "rgba(255,255,255,0.04)" : "rgba(0,0,0,0.04)" }}
            contentStyle={
              embedded
                ? { fontSize: 11, borderRadius: 10, border: "1px solid rgba(255,255,255,0.12)", background: "rgba(15,15,35,0.95)", color: "#e2e8f0" }
                : { fontSize: 11, borderRadius: 8, border: "1px solid #f3f4f6" }
            }
            formatter={(v) => [`${v} logins`, "Count"]}
          />
          <Bar dataKey="count" radius={[4, 4, 0, 0]}>
            {data.map((entry) => (
              <Cell key={entry.hour} fill={barFill(entry)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

const RISK_COLOR = { low: "#10b981", medium: "#f59e0b", high: "#ef4444" };
const RISK_BG = { low: "rgba(16,185,129,0.12)", medium: "rgba(245,158,11,0.15)", high: "rgba(239,68,68,0.15)" };

function LocationRow({ loc, index, embedded }) {
  return (
    <motion.div
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.05 }}
      className={
        embedded
          ? "flex items-center gap-3 border-b border-white/[0.06] py-2.5 last:border-0"
          : "flex items-center gap-3 border-b border-gray-50 py-2.5 last:border-0"
      }
    >
      <div
        className={
          embedded
            ? "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white/[0.06]"
            : "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-blue-50"
        }
      >
        <Globe size={15} className={embedded ? "text-cyan-300/90" : "text-blue-500"} />
      </div>
      <div className="min-w-0 flex-1">
        <p className={embedded ? "text-sm font-medium text-white" : "text-sm font-medium text-gray-900"}>
          {loc.city}, {loc.country}
        </p>
        <p className={embedded ? "text-xs text-gray-500" : "text-xs text-gray-400"}>
          {loc.count} sessions · last {fmtRelativeTime(loc.last_seen)}
        </p>
      </div>
      <span
        className="shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium"
        style={{ background: RISK_BG[loc.risk], color: RISK_COLOR[loc.risk] }}
      >
        {loc.risk}
      </span>
    </motion.div>
  );
}

const SEV_LIGHT = {
  high: { color: "#ef4444", bg: "#fef2f2", label: "High" },
  medium: { color: "#f59e0b", bg: "#fffbeb", label: "Medium" },
  low: { color: "#10b981", bg: "#ecfdf5", label: "Low" },
};
const SEV_DARK = {
  high: { color: "#fecaca", bg: "rgba(239,68,68,0.2)", label: "High" },
  medium: { color: "#fde68a", bg: "rgba(245,158,11,0.18)", label: "Medium" },
  low: { color: "#a7f3d0", bg: "rgba(16,185,129,0.15)", label: "Low" },
};

function AnomalyRow({ anomaly, index, embedded }) {
  const sev = (embedded ? SEV_DARK : SEV_LIGHT)[anomaly.severity] || (embedded ? SEV_DARK : SEV_LIGHT).low;
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.06 }}
      className={
        embedded
          ? "flex items-start gap-3 border-b border-white/[0.06] py-2.5 last:border-0"
          : "flex items-start gap-3 border-b border-gray-50 py-2.5 last:border-0"
      }
    >
      <div
        className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg"
        style={{ background: sev.bg }}
      >
        <AlertTriangle size={14} style={{ color: sev.color }} />
      </div>
      <div className="min-w-0 flex-1">
        <p className={embedded ? "text-sm font-medium text-white" : "text-sm font-medium text-gray-900"}>{anomaly.description}</p>
        <p className={embedded ? "text-xs text-gray-500" : "text-xs text-gray-400"}>{fmtRelativeTime(anomaly.ts)}</p>
      </div>
      <span
        className="shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold"
        style={{ background: sev.bg, color: sev.color }}
      >
        {sev.label}
      </span>
    </motion.div>
  );
}

function ActivityRow({ item, index, embedded }) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ delay: index * 0.04 }}
      className={embedded ? "flex items-center gap-3 border-b border-white/[0.05] py-2 last:border-0" : "flex items-center gap-3 py-2"}
    >
      <div
        className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${
          item.ok ? (embedded ? "bg-emerald-500/15" : "bg-green-50") : embedded ? "bg-rose-500/15" : "bg-red-50"
        }`}
      >
        {item.ok ? (
          <Activity size={13} className={embedded ? "text-emerald-300" : "text-green-500"} />
        ) : (
          <AlertTriangle size={13} className={embedded ? "text-rose-300" : "text-red-400"} />
        )}
      </div>
      <div className="min-w-0 flex-1">
        <p className={`text-xs font-medium ${item.ok ? (embedded ? "text-gray-300" : "text-gray-700") : embedded ? "text-rose-200" : "text-red-600"}`}>
          {item.action}
        </p>
        <p className={embedded ? "text-[10px] text-gray-500" : "text-[10px] text-gray-400"}>{item.channel}</p>
      </div>
      <span className={embedded ? "shrink-0 text-[10px] text-gray-600" : "shrink-0 text-[10px] text-gray-300"}>
        {fmtRelativeTime(item.ts)}
      </span>
    </motion.div>
  );
}

const BehaviorProfile = ({ userId = 1, onNavigate, embedded = false }) => {
  const { viewMode } = useViewMode();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [profileError, setProfileError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setProfileError(null);

    getBehaviorProfile(userId, viewMode)
      .then((res) => {
        if (!cancelled) {
          setData(res);
          setProfileError(null);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setData(null);
          setProfileError("Could not load behavior profile. Check that the API is running.");
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [userId, viewMode]);

  useEffect(() => {
    const handler = () => {
      setLoading(true);
      getBehaviorProfile(userId, viewMode)
        .then((res) => {
          setData(res);
          setProfileError(null);
        })
        .catch(() => setProfileError("Could not load behavior profile."))
        .finally(() => setLoading(false));
    };
    window.addEventListener("smartspend:data-updated", handler);
    window.addEventListener("dashboardModeChanged", handler);
    return () => {
      window.removeEventListener("smartspend:data-updated", handler);
      window.removeEventListener("dashboardModeChanged", handler);
    };
  }, [userId, viewMode]);

  const d = data;
  const highlightHours = useMemo(() => anomalyHighlightHours(d?.anomalies), [d?.anomalies]);

  const outer = embedded ? "mx-auto max-w-6xl space-y-5 pb-4" : "mx-auto max-w-3xl space-y-6 pb-8";

  return (
    <div className={outer}>
      {!embedded && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="flex items-start justify-between">
          <div>
            <div className="mb-1 flex items-center gap-2">
              {onNavigate && (
                <button
                  type="button"
                  onClick={() => onNavigate("trust-center")}
                  className="rounded-lg p-1 text-exiqo-glow/50 transition hover:bg-white/10 hover:text-exiqo-glow"
                  aria-label="Back to FraudShield overview"
                >
                  <ArrowLeft size={16} />
                </button>
              )}
              <h2 className="flex items-center gap-2 text-2xl font-bold text-white">
                <User size={22} className="text-purple-400" />
                Behavior profile
              </h2>
            </div>
            <p className="ml-8 mt-1 text-sm text-gray-400">Phase 2 — Feature store · 200+ behavioural signals</p>
          </div>
        </motion.div>
      )}

      {embedded && onNavigate && (
        <div className="flex justify-end">
          <button
            type="button"
            onClick={() => onNavigate("trust-center")}
            className="inline-flex items-center gap-1.5 rounded-xl border border-white/10 px-3 py-1.5 text-xs font-medium text-gray-400 transition hover:bg-white/[0.06] hover:text-white"
          >
            <ArrowLeft className="h-3.5 w-3.5" aria-hidden />
            Overview
          </button>
        </div>
      )}

      {loading ? (
        <RiskStatePlaceholder loading />
      ) : profileError ? (
        <RiskStatePlaceholder empty title="Behavior profile unavailable" message={profileError} />
      ) : !d || d?.empty ? (
        <RiskStatePlaceholder
          empty
          title="No behavior data in this view"
          message={
            d?.message ||
            "No transactions in this view yet. Upload a statement or switch merged / bank / card mode."
          }
        />
      ) : (
        <>
          <div className="grid gap-4 lg:grid-cols-2">
            <BehaviorRiskGauge risk={d.risk_score} embedded={embedded} />
            <TypicalPatternCard login_patterns={d.login_patterns} locations={d.locations} embedded={embedded} />
          </div>

          {d.login_patterns?.length > 0 && (
            <LoginPatternsChart data={d.login_patterns} embedded={embedded} highlightHours={highlightHours} />
          )}

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <div
              className={
                embedded
                  ? "rounded-2xl border border-white/10 bg-white/[0.03] p-5 backdrop-blur-xl lg:col-span-1"
                  : "rounded-2xl border border-gray-100 bg-white p-5 shadow-sm lg:col-span-1"
              }
            >
              <LocationPatternMap locations={d.locations} embedded={embedded} />
            </div>
            <div
              className={
                embedded
                  ? "rounded-2xl border border-white/10 bg-white/[0.03] p-5 backdrop-blur-xl lg:col-span-1"
                  : "rounded-2xl border border-gray-100 bg-white p-5 shadow-sm lg:col-span-1"
              }
            >
              <div className="mb-3 flex items-center gap-2">
                <MapPin size={15} className={embedded ? "text-sky-300" : "text-blue-500"} />
                <h3 className={embedded ? "text-sm font-semibold text-white" : "text-sm font-semibold text-gray-700"}>Location analysis</h3>
              </div>
              {d.locations?.length ? (
                d.locations.map((loc, i) => <LocationRow key={loc.city} loc={loc} index={i} embedded={embedded} />)
              ) : (
                <RiskStatePlaceholder empty message="No location data" compact />
              )}
            </div>
            <div
              className={
                embedded
                  ? "rounded-2xl border border-white/10 bg-white/[0.03] p-5 backdrop-blur-xl lg:col-span-1"
                  : "rounded-2xl border border-gray-100 bg-white p-5 shadow-sm lg:col-span-1"
              }
            >
              <div className="mb-3 flex items-center gap-2">
                <AlertTriangle size={15} className={embedded ? "text-amber-300" : "text-orange-400"} />
                <h3 className={embedded ? "text-sm font-semibold text-white" : "text-sm font-semibold text-gray-700"}>Detected anomalies</h3>
              </div>
              {d.anomalies?.length ? (
                d.anomalies.map((a, i) => <AnomalyRow key={a.id} anomaly={a} index={i} embedded={embedded} />)
              ) : (
                <RiskStatePlaceholder empty message="No anomalies detected" compact />
              )}
            </div>
          </div>

          <div
            className={
              embedded
                ? "rounded-2xl border border-white/10 bg-white/[0.03] p-5 backdrop-blur-xl"
                : "rounded-2xl border border-gray-100 bg-white p-5 shadow-sm"
            }
          >
            <div className="mb-3 flex items-center gap-2">
              <Clock size={15} className={embedded ? "text-violet-300" : "text-indigo-500"} />
              <h3 className={embedded ? "text-sm font-semibold text-white" : "text-sm font-semibold text-gray-700"}>Recent activity timeline</h3>
            </div>
            <div className={embedded ? "" : "divide-y divide-gray-50"}>
              {(d.recent_activity ?? []).slice(0, 10).map((item, i) => (
                <ActivityRow key={item.id} item={item} index={i} embedded={embedded} />
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
};

export default BehaviorProfile;
