import React, { useEffect, useMemo, useRef, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { ArrowDownRight, ArrowUpRight, Minus, RefreshCw } from "lucide-react";
import { getHealthHistory, getHealthNarrative } from "../../services/api";
import { EmptyState } from "../common/EmptyState";
import { GlassCard } from "../intro/GlassCard";
import PremiumCard from "../Dashboard/shared/PremiumCard";

const MONTH_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const WEAKEST_DOT_COLOR = "#A78BFA";

function weakestDotColor(components) {
  const comp = components || {};
  const items = [
    { points: Number(comp.savings_points ?? 0), max: 30, color: "#22c55e" },
    { points: Number(comp.anomaly_points ?? 0), max: 20, color: "#ef4444" },
    { points: Number(comp.expense_points ?? 0), max: 25, color: "#f59e0b" },
    { points: Number(comp.consistency_points ?? 0), max: 15, color: "#3b82f6" },
    { points: Number(comp.diversity_points ?? 0), max: 10, color: "#a855f7" },
  ];
  const weakest = items.reduce((min, x) => {
    const ratio = x.points / Math.max(x.max, 1);
    const minRatio = min.points / Math.max(min.max, 1);
    return ratio < minRatio ? x : min;
  }, items[0]);
  return weakest?.color || WEAKEST_DOT_COLOR;
}

function narrativeFromResponse(res) {
  const n = res?.narrative;
  if (typeof n === "string" && n.trim()) return n.trim();
  if (n && typeof n === "object") {
    const parts = [n.headline, n.score_explanation, n.motivational_message].filter(Boolean);
    if (parts.length) return parts.join(" ").slice(0, 320);
  }
  return null;
}

function scoreBarColor(score) {
  if (score >= 75) return "#22c55e";
  if (score >= 50) return "#f59e0b";
  return "#ef4444";
}

function HistorySparkline({ history, loading }) {
  const rows = Array.isArray(history) ? history.slice(-12) : [];
  if (loading) {
    return <div className="mt-4 h-16 animate-pulse rounded-lg bg-white/[0.06]" />;
  }
  if (!rows.length) return null;

  const barW = 14;
  const gap = 6;
  const chartH = 48;
  const svgW = rows.length * (barW + gap) - gap;

  return (
    <div className="mt-4 border-t border-white/[0.06] pt-4">
      <p className="mb-2 text-[10px] font-bold uppercase tracking-[0.12em] text-gray-500">12-month trend</p>
      <svg viewBox={`0 0 ${svgW} ${chartH + 18}`} width="100%" height={chartH + 18} aria-hidden>
        {rows.map((row, i) => {
          const score = Math.max(0, Math.min(100, Number(row.health_score ?? 0)));
          const h = (score / 100) * chartH;
          const x = i * (barW + gap);
          const y = chartH - h;
          const label = MONTH_SHORT[(Number(row.month) || 1) - 1] || "";
          return (
            <g key={`${row.year}-${row.month}-${i}`}>
              <rect
                x={x}
                y={y}
                width={barW}
                height={Math.max(h, 2)}
                rx={2}
                fill={scoreBarColor(score)}
                opacity={0.9}
              />
              <text
                x={x + barW / 2}
                y={chartH + 12}
                textAnchor="middle"
                fontSize="8"
                fill="rgba(255,255,255,0.4)"
              >
                {label}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

// ── Grade palette ──────────────────────────────────────────────────────────
const gradeColor = {
  A: "#22c55e",
  B: "#3b82f6",
  C: "#f59e0b",
  D: "#f97316",
  F: "#ef4444",
};

// Semicircle arc constants (viewBox 0 0 200 130)
// Center: (100,105), Radius: 80
// Arc: M 20 105 A 80 80 0 0 1 180 105
const ARC_PATH = "M 20 105 A 80 80 0 0 1 180 105";
const ARC_LENGTH = 251.3; // π × 80

// ── Trend badge ────────────────────────────────────────────────────────────
function TrendBadge({ trend }) {
  const up = trend === "IMPROVING";
  const down = trend === "DECLINING";
  const Icon = up ? ArrowUpRight : down ? ArrowDownRight : Minus;
  const cls = up
    ? "border-emerald-500/35 bg-emerald-500/10 text-emerald-300"
    : down
    ? "border-rose-500/35 bg-rose-500/10 text-rose-300"
    : "border-white/10 bg-white/[0.06] text-white/60";
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] font-semibold ${cls}`}>
      <Icon className="h-3.5 w-3.5" aria-hidden />
      {trend || "STABLE"}
    </span>
  );
}

// ── Sub-score bar ──────────────────────────────────────────────────────────
function Breakdown({ label, value, max, delayMs }) {
  const v =
    value === null || value === undefined || Number.isNaN(Number(value))
      ? null
      : Number(value);
  const ratio = v == null ? 0 : Math.max(0, Math.min(100, (v / max) * 100));
  const labelRight = v == null ? "—" : `${v}/${max}`;

  return (
    <div className="space-y-1">
      <div className="flex justify-between text-[11px]">
        <span className="text-white/60">{label}</span>
        <span className="tabular-nums font-semibold text-white/85">{labelRight}</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
        <motion.div
          className="h-full rounded-full"
          style={{
            background: "linear-gradient(90deg,#7C3AED,#A855F7,#22D3EE)",
          }}
          initial={{ width: 0 }}
          animate={{ width: `${ratio}%` }}
          transition={{
            duration: 0.9,
            delay: (delayMs || 0) / 1000,
            ease: [0.22, 1, 0.36, 1],
          }}
        />
      </div>
    </div>
  );
}

// ── Skeleton ───────────────────────────────────────────────────────────────
function GaugeSkeleton() {
  return (
    <div className="space-y-3 py-4">
      <div className="mx-auto h-36 w-56 animate-pulse rounded-full bg-white/[0.06]" />
      <div className="space-y-2.5 pt-2">
        {[1, 2, 3, 4, 5].map((k) => (
          <div key={k} className="h-2 w-full animate-pulse rounded-full bg-white/[0.06]" />
        ))}
      </div>
    </div>
  );
}

// ── Custom SVG gauge ───────────────────────────────────────────────────────
function SvgGauge({ displayScore, score, grade, reduce }) {
  const filled = reduce
    ? (score / 100) * ARC_LENGTH
    : (displayScore / 100) * ARC_LENGTH;
  const gColor = gradeColor[grade] || "#ef4444";

  return (
    <div className="mx-auto" style={{ maxWidth: 260 }}>
      <svg
        viewBox="0 0 200 130"
        width="100%"
        style={{ overflow: "visible" }}
        aria-label={`Financial health score: ${displayScore} out of 100`}
      >
        <defs>
          <linearGradient id="hsg-grad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#7C3AED" />
            <stop offset="50%" stopColor="#A855F7" />
            <stop offset="100%" stopColor="#06b6d4" />
          </linearGradient>
        </defs>

        {/* Track */}
        <path
          d={ARC_PATH}
          stroke="rgba(255,255,255,0.07)"
          strokeWidth="13"
          fill="none"
          strokeLinecap="round"
        />

        {/* Filled arc — animated via strokeDasharray */}
        <path
          d={ARC_PATH}
          stroke="url(#hsg-grad)"
          strokeWidth="13"
          fill="none"
          strokeLinecap="round"
          strokeDasharray={`${filled} ${ARC_LENGTH}`}
          style={{ transition: "stroke-dasharray 1.5s cubic-bezier(0.22,1,0.36,1)" }}
        />

        {/* Score number */}
        <text
          x="100"
          y="90"
          textAnchor="middle"
          fontSize="42"
          fontWeight="800"
          fill="white"
          fontFamily="inherit"
          style={{ letterSpacing: "-2px" }}
        >
          {displayScore}
        </text>

        {/* "out of 100" */}
        <text
          x="100"
          y="110"
          textAnchor="middle"
          fontSize="11"
          fill="rgba(255,255,255,0.42)"
          fontFamily="inherit"
        >
          out of 100
        </text>

        {/* Grade pill */}
        <rect
          x="82"
          y="116"
          width="36"
          height="14"
          rx="7"
          fill={gColor}
          opacity="0.9"
        />
        <text
          x="100"
          y="126.5"
          textAnchor="middle"
          fontSize="8"
          fontWeight="700"
          fill="white"
          fontFamily="inherit"
          letterSpacing="1"
        >
          {grade}
        </text>
      </svg>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────
/**
 * @param {{
 *   userId?: number;
 *   month?: number;
 *   year?: number;
 *   healthData?: Record<string, unknown>;
 *   narration?: string;
 *   variant?: "default" | "hero";
 *   loading?: boolean;
 *   loadError?: boolean;
 *   onRetry?: () => void;
 *   showRecommendations?: boolean;
 *   showNarrative?: boolean;
 *   showHistory?: boolean;
 * }} props
 */
const HealthScoreGauge = ({
  userId,
  month,
  year,
  healthData = {},
  narration,
  variant = "default",
  loading = false,
  loadError = false,
  onRetry,
  showRecommendations = false,
  showNarrative = false,
  showHistory = false,
}) => {
  const reduce = useReducedMotion();
  const rawScore = healthData.score;
  const insufficientData =
    healthData?.reason === "not_enough_data" || rawScore == null || rawScore === undefined;
  const [displayScore, setDisplayScore] = useState(0);
  const rafRef = useRef(null);

  const grade = healthData.grade || "F";
  const comp = healthData.components || {};
  const trend = healthData.trend || "STABLE";
  const recommendations = Array.isArray(healthData.recommendations) ? healthData.recommendations : [];
  const recDotColor = useMemo(() => weakestDotColor(comp), [comp]);

  const [fetchedNarrative, setFetchedNarrative] = useState(null);
  const [narrativeLoading, setNarrativeLoading] = useState(false);
  const [history, setHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  const targetScore = loadError || loading ? 0 : Number(rawScore || 0);

  useEffect(() => {
    if (!showNarrative || narration || !userId || !month || !year) {
      setFetchedNarrative(null);
      return;
    }
    let cancelled = false;
    setNarrativeLoading(true);
    getHealthNarrative(userId, month, year)
      .then((res) => {
        if (!cancelled) setFetchedNarrative(narrativeFromResponse(res));
      })
      .catch(() => {
        if (!cancelled) setFetchedNarrative(null);
      })
      .finally(() => {
        if (!cancelled) setNarrativeLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [showNarrative, narration, userId, month, year]);

  useEffect(() => {
    if (!showHistory || !userId) {
      setHistory([]);
      return;
    }
    let cancelled = false;
    setHistoryLoading(true);
    getHealthHistory(userId)
      .then((rows) => {
        if (!cancelled) setHistory(Array.isArray(rows) ? rows : []);
      })
      .catch(() => {
        if (!cancelled) setHistory([]);
      })
      .finally(() => {
        if (!cancelled) setHistoryLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [showHistory, userId]);

  const narrativeLine =
    narration ||
    fetchedNarrative ||
    (showNarrative && !narrativeLoading && recommendations[0] ? String(recommendations[0]) : null);

  // Animate score from 0 → targetScore using requestAnimationFrame
  useEffect(() => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current);

    if (loading || loadError || reduce || !targetScore) {
      setDisplayScore(targetScore);
      return;
    }

    setDisplayScore(0);
    const startTime = performance.now();
    const duration = 1500;

    function frame(now) {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      // ease-out-cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplayScore(Math.round(eased * targetScore));
      if (progress < 1) {
        rafRef.current = requestAnimationFrame(frame);
      }
    }

    // Small delay so the arc transition is visible
    const tid = setTimeout(() => {
      rafRef.current = requestAnimationFrame(frame);
    }, 120);

    return () => {
      clearTimeout(tid);
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [targetScore, loading, loadError, reduce]);

  // ── Sub-scores ─────────────────────────────────────────────────────────
  const breakdowns = [
    { label: "Savings Rate", value: comp.savings_points, max: 30, delay: 0 },
    { label: "Security", value: comp.anomaly_points, max: 20, delay: 200 },
    { label: "Expense Ratio", value: comp.expense_points, max: 25, delay: 400 },
    { label: "Consistency", value: comp.consistency_points, max: 15, delay: 600 },
    { label: "Diversity", value: comp.diversity_points, max: 10, delay: 800 },
  ];

  // ── Error state ─────────────────────────────────────────────────────────
  if (loadError) {
    return (
      <GlassCard padding="md" surface="panel" className="border-white/[0.08]">
        <div className="mb-3 flex items-center justify-between gap-2">
          <div>
            <p className="text-[11px] font-bold uppercase tracking-[0.15em] text-gray-500">Financial Health</p>
            <h3 className="font-heading text-base font-semibold text-white">Health Score</h3>
          </div>
        </div>
        <div className="flex flex-col items-center py-8 text-center">
          <div
            className="mb-3 flex items-center justify-center rounded-full"
            style={{ width: 56, height: 56, background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)" }}
          >
            <span className="text-2xl font-bold text-rose-400">—</span>
          </div>
          <p className="text-xs text-amber-100/80 max-w-[180px]">Could not load your health score.</p>
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="mt-4 inline-flex items-center gap-2 rounded-xl border border-amber-400/35 bg-amber-500/10 px-4 py-2 text-xs font-semibold text-amber-50 hover:bg-amber-500/20 transition-colors"
            >
              <RefreshCw className="h-3.5 w-3.5" aria-hidden />
              Try Again
            </button>
          )}
        </div>
        <div className="mt-4 space-y-3 border-t border-white/[0.06] pt-4">
          {breakdowns.map(({ label, max, delay }, i) => (
            <Breakdown key={label} label={label} value={null} max={max} delayMs={i * 200} />
          ))}
        </div>
      </GlassCard>
    );
  }

  if (insufficientData && !loading && !loadError) {
    return (
      <GlassCard padding="md" surface="panel" className="border-white/[0.08]">
        <EmptyState
          icon="📊"
          title="Health Score Not Available Yet"
          subtitle={healthData.message || "Upload more statements to calculate your Health Score"}
          hint={
            healthData.days_needed
              ? `Upload about ${healthData.days_needed} days of data (${healthData.days_available ?? 0} days available)`
              : undefined
          }
        />
      </GlassCard>
    );
  }

  // ── Loading state ────────────────────────────────────────────────────────
  if (loading) {
    return (
      <GlassCard padding="md" surface="panel" className="border-white/[0.08]">
        <div className="mb-3 flex items-center justify-between gap-2">
          <div>
            <p className="text-[11px] font-bold uppercase tracking-[0.15em] text-gray-500">Financial Health</p>
            <h3 className="font-heading text-base font-semibold text-white">Health Score</h3>
          </div>
          <span className="h-6 w-20 animate-pulse rounded-full bg-white/[0.06]" />
        </div>
        <GaugeSkeleton />
      </GlassCard>
    );
  }

  // ── Hero variant (used on Dashboard hero) ───────────────────────────────
  if (variant === "hero") {
    return (
      <PremiumCard variant="purple" topAccent interactive={false}>
        <div className="mb-2 flex items-center justify-between gap-2">
          <h3 className="font-heading text-sm font-semibold text-white sm:text-base">Financial health</h3>
          <TrendBadge trend={trend} />
        </div>
        <SvgGauge displayScore={displayScore} score={targetScore} grade={grade} reduce={reduce} />
        {(narration || (showNarrative && narrativeLine)) && (
          <p className="mt-2 text-center text-sm leading-relaxed text-white/70 line-clamp-4">
            {narration || narrativeLine}
          </p>
        )}
      </PremiumCard>
    );
  }

  // ── Default variant ──────────────────────────────────────────────────────
  return (
    <GlassCard padding="md" surface="panel" className="border-white/[0.08]">
      {/* Header */}
      <div className="mb-3 flex items-center justify-between gap-2">
        <div>
          <p className="text-[11px] font-bold uppercase tracking-[0.15em] text-gray-500">Financial Health</p>
          <h3 className="font-heading text-base font-semibold text-white">Health Score</h3>
        </div>
        {/* STABLE / IMPROVING / DECLINING badge */}
        <TrendBadge trend={trend} />
      </div>

      {/* SVG Gauge */}
      <SvgGauge displayScore={displayScore} score={targetScore} grade={grade} reduce={reduce} />

      {/* Sub-score bars */}
      <div className="mt-5 space-y-3 border-t border-white/[0.06] pt-4">
        {breakdowns.map(({ label, value, max, delay }) => (
          <Breakdown key={label} label={label} value={value} max={max} delayMs={delay} />
        ))}
      </div>

      {showNarrative && narrativeLine ? (
        <p className="mt-3 text-[13px] leading-relaxed text-white/45">{narrativeLine}</p>
      ) : null}
      {showNarrative && narrativeLoading && !narration ? (
        <p className="mt-3 h-4 w-4/5 animate-pulse rounded bg-white/[0.06]" />
      ) : null}

      {showRecommendations && recommendations.length > 0 ? (
        <ul className="mt-4 space-y-2 border-t border-white/[0.06] pt-3">
          {recommendations.map((text, i) => (
            <li key={i} className="flex items-start gap-2 text-xs leading-relaxed text-white/75">
              <span
                className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full"
                style={{ backgroundColor: recDotColor }}
                aria-hidden
              />
              <span>{text}</span>
            </li>
          ))}
        </ul>
      ) : null}

      {showHistory ? <HistorySparkline history={history} loading={historyLoading} /> : null}
    </GlassCard>
  );
};

export default HealthScoreGauge;
