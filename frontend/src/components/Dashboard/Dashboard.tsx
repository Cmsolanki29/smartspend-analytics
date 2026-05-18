/**
 * Summary dashboard: KPIs, health, guardian shortcuts, charts only.
 * AI Guardian + inline anomalies/transactions removed (duplicates Insights, Simulator,
 * FraudShield, Transactions tabs). Readability: opaque `GlassCard surface="panel"` on charts;
 * Aurora variant="app" + solid TopBar in shell.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion, useInView, useReducedMotion } from "framer-motion";
import {
  BadgeCheck,
  Landmark,
  PiggyBank,
  Receipt,
  RefreshCw,
  Shield,
  Sparkles,
  Wallet,
} from "lucide-react";
import useSmartSpend from "../../hooks/useSmartSpend";
import { humanizeVerdictReason } from "../../utils/subscriptionVerdictCopy";
import { useAuth } from "../../context/AuthContext";
import { useViewMode } from "../../context/ViewModeContext";
import {
  apiUtils,
  getDarkPatterns,
  getEmiReport,
  getFestivals,
  getFraudShieldAlerts,
  getDashboardSummary,
  getHealthNarrative,
  getSubscriptions,
} from "../../services/api";
import { getAISummary } from "../../services/subscriptionIntelligence";
import HealthScoreGauge from "../Charts/HealthScoreGauge";
import MonthlyTrendChart from "../Charts/MonthlyTrendChart";
import SpendingPieChart from "../Charts/SpendingPieChart";
import { ErrorCard } from "../common/ErrorCard";
import { GlassCard } from "../intro/GlassCard";
import { SkeletonStats } from "../common/SkeletonCard";
import DashboardGreeting from "./DashboardGreeting";
import KPICard from "./shared/KPICard";
import QuickActionCard from "./shared/QuickActionCard";
import PremiumCard from "./shared/PremiumCard";
import AIFinancialCommandCenter, { type CommandCard } from "./AIFinancialCommandCenter";

const monthKey = (y: number, m: number) => `${y}-${String(m).padStart(2, "0")}`;

// ── Source Breakdown Card ─────────────────────────────────────────────────────

type BreakdownSource = { type: string; name: string; spend: number };
type BreakdownData = {
  mode: string;
  sources: BreakdownSource[];
  total_spend: number;
};

function SourceBreakdownCard({ userId }: { userId: number }) {
  const { viewMode } = useViewMode();
  const [breakdown, setBreakdown] = useState<BreakdownData | null>(null);
  const [loadingBd, setLoadingBd] = useState(true);

  const fetchBreakdown = useCallback(async () => {
    setLoadingBd(true);
    try {
      const qs = new URLSearchParams({ user_id: String(userId), scope: viewMode });
      const res = await fetch(`/api/dashboard/source-breakdown?${qs}`);
      if (!res.ok) return;
      const data: BreakdownData = await res.json();
      setBreakdown(data);
    } catch {
      /* non-critical — silently ignore */
    } finally {
      setLoadingBd(false);
    }
  }, [userId, viewMode]);

  useEffect(() => {
    fetchBreakdown();
  }, [fetchBreakdown]);

  if (loadingBd || !breakdown || breakdown.sources.length === 0) return null;

  const { sources, total_spend } = breakdown;
  const fmt = (n: number) =>
    new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(n);

  return (
    <div className="mt-4 rounded-2xl border border-white/[0.08] bg-[#0c1022]/80 p-5">
      <h3 className="mb-4 text-sm font-semibold uppercase tracking-wide text-white/50">
        📊 Spending Breakdown
      </h3>

      {sources.length === 1 ? (
        /* Single source — simple summary */
        <div className="flex items-end gap-4">
          <div>
            <p className="font-heading text-3xl font-bold text-white">{fmt(sources[0].spend)}</p>
            <p className="mt-1 text-sm text-white/45">
              {sources[0].type === "credit_card" ? "💳" : "🏦"} {sources[0].name} — this month
            </p>
          </div>
        </div>
      ) : (
        /* Multi source — bar breakdown */
        <div className="space-y-3">
          {sources.map((src) => {
            const pct = total_spend > 0 ? Math.round((src.spend / total_spend) * 100) : 0;
            const isCard = src.type === "credit_card";
            return (
              <div key={src.type} className="grid items-center gap-3" style={{ gridTemplateColumns: "140px 1fr 90px" }}>
                <div className="flex items-center gap-2 text-sm text-white/70">
                  <span
                    className={`grid h-6 w-6 shrink-0 place-items-center rounded-md text-sm ${
                      isCard ? "bg-violet-500/20" : "bg-cyan-500/20"
                    }`}
                  >
                    {isCard ? "💳" : "🏦"}
                  </span>
                  <span className="truncate">{src.name}</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-white/[0.06]">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${
                      isCard
                        ? "bg-gradient-to-r from-violet-500 to-purple-600"
                        : "bg-gradient-to-r from-cyan-500 to-sky-600"
                    }`}
                    style={{ width: `${pct}%` }}
                  />
                </div>
                <p className="text-right font-heading text-sm font-semibold tabular-nums text-white">
                  {fmt(src.spend)}
                </p>
              </div>
            );
          })}

          <div className="mt-2 flex items-center justify-between border-t border-white/[0.06] pt-3">
            <span className="text-sm font-semibold text-white/60">Combined total</span>
            <span className="font-heading text-base font-bold text-emerald-300">{fmt(total_spend)}</span>
          </div>
        </div>
      )}

    </div>
  );
}

type TrendPoint = { month: string; income?: number; expense?: number; saved?: number };

type NextFest = { name: string; days_remaining: number } | null;

type DashboardProps = {
  userId: number;
  month: number;
  year: number;
  onMonthChange?: (m: number) => void;
  onYearChange?: (y: number) => void;
  userName?: string;
  setActiveTab?: (tab: string) => void;
};

export default function Dashboard({
  userId,
  month,
  year,
  userName = "there",
  setActiveTab,
}: DashboardProps) {
  const reduce = useReducedMotion();
  const { user: authUser } = useAuth();
  const { viewMode } = useViewMode();
  const { spending, trends, health, loading, error, loadWarnings, refetch } = useSmartSpend(
    userId,
    month,
    year
  );
  const trendList = useMemo(() => (Array.isArray(trends) ? trends : []) as TrendPoint[], [trends]);

  const canLiveIntel = Boolean(authUser?.id && Number(authUser.id) === Number(userId));
  const [aiIntel, setAiIntel] = useState<{
    loading: boolean;
    summary: Awaited<ReturnType<typeof getAISummary>> | null;
  }>({ loading: false, summary: null });

  const [intel, setIntel] = useState({
    loading: true,
    fraudPending: 0,
    monthlyWaste: 0,
    nextFest: null as NextFest,
    darkCount: 0,
    emiCount: 0,
  });

  const [narration, setNarration] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date>(() => new Date());
  const [statementSpend, setStatementSpend] = useState<number | null>(null);

  const row3Ref = useRef<HTMLElement | null>(null);
  const r3 = useInView(row3Ref, { once: true, amount: 0.2 });

  const onDataRefresh = useCallback(async () => {
    await refetch();
    setLastRefresh(new Date());
  }, [refetch]);

  const loadIntel = useCallback(async () => {
    setIntel((s) => ({ ...s, loading: true }));
    try {
      const [alertsRes, subsRes, festRes, darkRes, emiRes] = await Promise.all([
        getFraudShieldAlerts(userId),
        getSubscriptions(userId),
        getFestivals(userId),
        getDarkPatterns(userId).catch(() => []),
        getEmiReport(userId).catch(() => ({ emis_detected: [] })),
      ]);
      const pending = (alertsRes?.alerts || []).filter((a: { user_action?: string }) => a.user_action === "PENDING").length;
      const waste = Number(subsRes?.monthly_waste || 0);
      const nf = festRes?.next_festival || null;
      const darkList = darkRes?.patterns || (Array.isArray(darkRes) ? darkRes : []) || [];
      const darkCount = Array.isArray(darkList) ? darkList.length : 0;
      const emis = emiRes?.emis_detected || emiRes?.emis || [];
      const emiCount = Array.isArray(emis) ? emis.length : Number(emiRes?.emi_detected_count || 0);

      setIntel({ loading: false, fraudPending: pending, monthlyWaste: waste, nextFest: nf, darkCount, emiCount });
    } catch {
      setIntel({ loading: false, fraudPending: 0, monthlyWaste: 0, nextFest: null, darkCount: 0, emiCount: 0 });
    }
  }, [userId]);

  useEffect(() => {
    loadIntel();
  }, [loadIntel]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const dash = (await getDashboardSummary(userId)) as {
          statement_period_spend?: number;
        };
        if (!cancelled) {
          const sp = Number(dash?.statement_period_spend ?? 0);
          setStatementSpend(sp > 0 ? sp : null);
        }
      } catch {
        if (!cancelled) setStatementSpend(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [userId]);

  useEffect(() => {
    const handler = () => {
      loadIntel();
      refetch();
      getDashboardSummary(userId)
        .then((dash: { statement_period_spend?: number }) => {
          const sp = Number(dash?.statement_period_spend ?? 0);
          setStatementSpend(sp > 0 ? sp : null);
        })
        .catch(() => setStatementSpend(null));
    };
    window.addEventListener("dashboardModeChanged", handler);
    window.addEventListener("smartspend:data-updated", handler);
    return () => {
      window.removeEventListener("dashboardModeChanged", handler);
      window.removeEventListener("smartspend:data-updated", handler);
    };
  }, [loadIntel, userId, refetch]);

  // Refresh health score + KPIs when EMI/purchase/festival data changes
  useEffect(() => {
    const handler = () => {
      refetch();
      loadIntel();
    };
    window.addEventListener("smartspend:health-score-changed", handler);
    window.addEventListener("smartspend:purchase-goals-changed", handler);
    window.addEventListener("smartspend-financial-sync", handler);
    return () => {
      window.removeEventListener("smartspend:health-score-changed", handler);
      window.removeEventListener("smartspend:purchase-goals-changed", handler);
      window.removeEventListener("smartspend-financial-sync", handler);
    };
  }, [refetch, loadIntel]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await getHealthNarrative(userId, month, year);
        const text = typeof res?.narrative === "string" ? res.narrative : res?.narrative?.summary;
        if (!cancelled) setNarration(text || null);
      } catch {
        if (!cancelled) setNarration(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [userId, month, year]);

  useEffect(() => {
    if (!canLiveIntel || !authUser?.id) {
      setAiIntel({ loading: false, summary: null });
      return;
    }
    let cancelled = false;
    (async () => {
      setAiIntel((s) => ({ ...s, loading: true }));
      try {
        const sum = await getAISummary(authUser.id);
        if (!cancelled) {
          setAiIntel({ loading: false, summary: sum });
        }
      } catch {
        if (!cancelled) setAiIntel({ loading: false, summary: null });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [canLiveIntel, authUser?.id]);


  const trendRow = useMemo(() => {
    const key = monthKey(year, month);
    return trendList.find((t) => t.month === key) || null;
  }, [trendList, month, year]);

  const prevMonthExpense = useMemo(() => {
    const key = monthKey(year, month);
    const idx = trendList.findIndex((t) => t.month === key);
    if (idx <= 0) return 0;
    return Number(trendList[idx - 1]?.expense || 0);
  }, [trendList, month, year]);

  const monthSpend = useMemo(() => {
    if (viewMode === "credit_card_only" && statementSpend != null) {
      return statementSpend;
    }
    const fromTrend = Number(trendRow?.expense || 0);
    if (fromTrend > 0) return fromTrend;
    return (Array.isArray(spending) ? spending : []).reduce((acc: number, row: { total_amount?: number }) => acc + Number(row.total_amount || 0), 0);
  }, [trendRow, spending, viewMode, statementSpend]);

  const monthIncome = useMemo(() => Number(trendRow?.income || 0), [trendRow]);

  const netMonth = useMemo(() => {
    if (!trendRow) return 0;
    // Match KPI subtitle: net of credits − debits (API `saved` clamps at 0 for “savings” semantics).
    return Number(trendRow.income || 0) - Number(trendRow.expense || 0);
  }, [trendRow]);

  const savedYtd = useMemo(() => {
    return trendList
      .filter((t) => String(t.month || "").startsWith(`${year}-`))
      .reduce((acc: number, t) => acc + Number(t.saved || 0), 0);
  }, [trendList, year]);

  const sparkExpense = useMemo(() => {
    return trendList.slice(-6).map((t) => Number(t.expense || 0));
  }, [trendList]);

  const spendDeltaPct = useMemo(() => {
    if (prevMonthExpense <= 0) return null;
    return ((monthSpend - prevMonthExpense) / prevMonthExpense) * 100;
  }, [monthSpend, prevMonthExpense]);

  const netDeltaPct = useMemo(() => {
    const key = monthKey(year, month);
    const idx = trendList.findIndex((t) => t.month === key);
    if (idx <= 0) return null;
    const prev = Number(trendList[idx - 1]?.saved || 0);
    if (prev === 0) return null;
    return ((netMonth - prev) / Math.abs(prev)) * 100;
  }, [trendList, month, year, netMonth]);

  const savedSpark = useMemo(() => {
    return trendList.slice(-6).map((t) => Number(t.saved || 0));
  }, [trendList]);

  const healthRec = health && typeof health === "object" && "recommendations" in health ? (health as { recommendations?: string[] }).recommendations : undefined;
  const healthNarrationLine =
    narration || (Array.isArray(healthRec) && healthRec[0]) || "Your guardian is monitoring cashflow, subscriptions, and anomalies.";

  const healthComp =
    health && typeof health === "object" && "components" in health
      ? ((health as { components?: Record<string, number> }).components || {})
      : {};

  const commandCards = useMemo((): CommandCard[] => {
    const goSubs = () => setActiveTab?.("subscriptions");
    const goFraud = () => setActiveTab?.("fraud");
    const goInsights = () => setActiveTab?.("insights");
    const out: CommandCard[] = [];

    if (canLiveIntel && aiIntel.summary?.success) {
      const sum = aiIntel.summary;
      const s = sum.summary;
      const v = sum.verdicts || {};
      const declining = (v.declining || []) as Array<Record<string, unknown>>;
      const dormant = (v.dormant || []) as Array<Record<string, unknown>>;
      const firstRisk = declining[0] || dormant[0];
      const waste = Number(s?.verdict_monthly_waste_sum_inr || 0);
      const atRisk = Number(s?.at_risk_count || 0);
      if (atRisk > 0 || waste > 0.01) {
        out.push({
          id: "risk-waste",
          urgency: "critical",
          badge: "CRITICAL",
          title: firstRisk
            ? `Review ${String(firstRisk.subscription_name || "subscription")}`
            : "Subscriptions to review",
          body: humanizeVerdictReason(
            String(firstRisk?.reasoning || ""),
            String(firstRisk?.verdict || "declining")
          ) || "Usage dropped or you rarely open this app — worth checking before the next bill.",
          metricLabel: "Possible savings",
          metricValue: `${apiUtils.formatINR(waste)}/mo`,
          ctaLabel: "Review",
          onCta: goSubs,
        });
      }
      const upgrades = (v.upgrade_recommended || []) as Array<Record<string, unknown>>;
      const u0 = upgrades[0];
      if (u0) {
        out.push({
          id: "upgrade",
          urgency: "opportunity",
          badge: "Opportunity",
          title: `${String(u0.subscription_name || "Subscription")} — paid plan may help`,
          body: humanizeVerdictReason(
            String(u0.reasoning || ""),
            "upgrade_recommended"
          ) || "You use this app a lot — a paid plan might be worth it.",
          metricLabel: "Last 30 days",
          metricValue: `${Number(u0.current_usage_hours || 0).toFixed(0)}h`,
          ctaLabel: "Review",
          onCta: goSubs,
        });
      }
      const mig = (sum.migrations || []) as Array<Record<string, unknown>>;
      const m0 = mig[0];
      if (m0 && out.length < 3) {
        out.push({
          id: "migration",
          urgency: "warning",
          badge: "MIGRATION",
          title: String(m0.title || "Category shift"),
          body: String(m0.description || "We detected a usage migration in the same category."),
          metricLabel: "Save up to",
          metricValue: `${apiUtils.formatINR(Number(m0.potential_savings_monthly || 0))}/mo`,
          ctaLabel: "Subscriptions",
          onCta: goSubs,
        });
      }
      if (out.length < 3) {
        const ytdSave = Number(s?.savings_amount_saved_ytd_inr || 0);
        out.push({
          id: "savings-ytd",
          urgency: "safe",
          badge: "OPTIMIZATION",
          title: "Year-to-date subscription savings",
          body: "Ledgered wins from cancellations and prevention.",
          metricLabel: "Saved YTD",
          metricValue: apiUtils.formatINR(ytdSave),
          ctaLabel: "Details",
          onCta: goSubs,
        });
      }
      return out.slice(0, 3);
    }

    if (intel.monthlyWaste > 0.01) {
      out.push({
        id: "waste-fallback",
        urgency: "warning",
        badge: "Warning",
        title: "Possible subscription waste",
        body: "Leakage flagged for this workspace view.",
        metricLabel: "Est. monthly waste",
        metricValue: apiUtils.formatINR(intel.monthlyWaste),
        ctaLabel: "Subscriptions",
        onCta: goSubs,
      });
    }
    if (intel.fraudPending > 0) {
      out.push({
        id: "fraud",
        urgency: "critical",
        badge: "CRITICAL",
        title: `${intel.fraudPending} FraudShield alert${intel.fraudPending > 1 ? "s" : ""}`,
        body: "Review before large transfers or new payees.",
        metricLabel: "Queue",
        metricValue: String(intel.fraudPending),
        ctaLabel: "Open FraudShield",
        onCta: goFraud,
      });
    }
    out.push({
      id: "intel-tip",
      urgency: "info",
      badge: "Info",
      title: canLiveIntel ? "Signals warming up" : "Live subscription AI",
      body: canLiveIntel
        ? "We will populate this rail as new verdicts and migrations arrive."
        : "Switch the workspace selector to your signed-in user to stream subscription intelligence here.",
      ctaLabel: canLiveIntel ? "Insights" : "Transactions",
      onCta: canLiveIntel ? goInsights : () => setActiveTab?.("transactions"),
    });
    return out.slice(0, 3);
  }, [canLiveIntel, aiIntel.summary, intel.monthlyWaste, intel.fraudPending, setActiveTab]);

  const aiSignalCount = useMemo(() => {
    let n = 0;
    if (canLiveIntel && aiIntel.summary?.success) {
      const s = aiIntel.summary.summary;
      n += Number(s?.at_risk_count || 0) > 0 ? 1 : 0;
      n += Number(s?.migrations_detected || 0) > 0 ? 1 : 0;
      n += Number(s?.upgrade_recommended_count || 0) > 0 ? 1 : 0;
      n += 4;
    } else {
      n = 3 + (intel.fraudPending > 0 ? 2 : 0) + (intel.monthlyWaste > 0 ? 1 : 0);
    }
    return Math.max(4, Math.min(14, n));
  }, [canLiveIntel, aiIntel.summary, intel.fraudPending, intel.monthlyWaste]);

  if (loading) {
    return (
      <main className="relative mx-auto max-w-[1600px] px-0 pb-24 pt-2 md:pb-8">
        <GlassCard surface="panel" className="mb-4 border-white/[0.08]">
          <SkeletonStats />
        </GlassCard>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <GlassCard key={i} surface="panel" padding="sm" className="h-48 animate-ss-shimmer bg-[length:200%_100%]">
              <div className="h-4 w-1/3 rounded bg-white/[0.06]" />
              <div className="mt-6 h-8 w-2/3 rounded bg-white/[0.06]" />
            </GlassCard>
          ))}
        </div>
      </main>
    );
  }

  if (error) {
    return (
      <main className="relative mx-auto max-w-[1600px] px-0 pt-2">
        <ErrorCard message={error} onRetry={onDataRefresh} />
      </main>
    );
  }

  const fadeIn = { initial: reduce ? false : { opacity: 0, y: 14 }, animate: { opacity: 1, y: 0 } };

  return (
    <motion.main
      className="relative mx-auto max-w-[1600px] px-0 pb-28 pt-1 md:pb-10"
      initial={reduce ? false : { opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: reduce ? 0.15 : 0.4, ease: [0.22, 1, 0.36, 1] }}
    >
      {Array.isArray(loadWarnings) &&
      loadWarnings.length > 0 &&
      !trendList.length &&
      !(Array.isArray(spending) && spending.length > 0) ? (
        <div
          role="status"
          className="mb-4 rounded-xl border border-amber-400/25 bg-amber-500/10 px-4 py-2.5 text-sm text-amber-50/95"
        >
          <span className="font-semibold text-amber-100">Charts still loading — </span>
          Data will appear shortly. If this persists, run{" "}
          <code className="rounded bg-black/30 px-1 text-xs">.\start-dev.ps1</code> and refresh.
        </div>
      ) : null}
      {canLiveIntel && viewMode === "credit_card_only" ? (
        <div
          role="status"
          className="mb-4 flex flex-col gap-3 rounded-xl border border-amber-400/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-50 sm:flex-row sm:items-center sm:justify-between"
        >
          <div>
            <p className="font-semibold text-amber-100">Card-only dashboard</p>
            <p className="mt-0.5 text-amber-50/90">
              Income and bank-only KPIs are hidden. Add a bank or switch to merged view in Settings → Connected
              accounts.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setActiveTab?.("settings")}
            className="shrink-0 rounded-lg border border-amber-300/40 bg-amber-500/20 px-4 py-2 text-xs font-semibold text-amber-50 hover:bg-amber-500/30"
          >
            Open Settings
          </button>
        </div>
      ) : null}
      <DashboardGreeting
        lastSync={lastRefresh}
        loading={loading}
        monthSpend={monthSpend}
        monthIncome={monthIncome}
        fraudPending={intel.fraudPending}
        savedYtd={savedYtd}
      />

      <AIFinancialCommandCenter
        signalCount={aiSignalCount}
        cards={commandCards}
        loading={Boolean(canLiveIntel && aiIntel.loading)}
        aiActive={canLiveIntel && !aiIntel.loading && Boolean(aiIntel.summary?.success)}
      />

      {/* Row 1 — KPIs + health */}
      <section className="mt-6 grid grid-cols-1 gap-4 xl:grid-cols-12 xl:gap-6">
        <div className="space-y-4 xl:col-span-7">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <KPICard
              variant="purple"
              label="Available Balance"
              value={netMonth}
              formatValue={(n) => apiUtils.formatINR(n)}
              subtitle="Net of credits − debits this month"
              icon={Wallet}
              trendPct={netDeltaPct}
              sparkline={sparkExpense}
              delay={0}
            />
            <KPICard
              variant="rose"
              label={viewMode === "credit_card_only" ? "Card Statement Spend" : "This Month Spend"}
              value={monthSpend}
              formatValue={(n) => apiUtils.formatINR(n)}
              subtitle={
                viewMode === "credit_card_only"
                  ? "Total on uploaded card statement(s)"
                  : `${month}/${year}`
              }
              icon={Receipt}
              trendPct={spendDeltaPct}
              sparkline={sparkExpense}
              delay={reduce ? 0 : 0.08}
            />
            <KPICard
              variant="emerald"
              label="Saved This Year"
              value={savedYtd}
              formatValue={(n) => apiUtils.formatINR(n)}
              subtitle="Sum of monthly savings in calendar year"
              icon={PiggyBank}
              sparkline={savedSpark}
              delay={reduce ? 0 : 0.16}
            />
          </div>
          <SourceBreakdownCard userId={userId} />
        </div>

        <div className="space-y-4 xl:col-span-5">
          <HealthScoreGauge
            userId={userId}
            month={month}
            year={year}
            healthData={health ?? {}}
            narration={healthNarrationLine}
            variant="hero"
            showRecommendations={false}
            showNarrative
            showHistory={false}
          />
          {Object.keys(healthComp).length > 0 ? (
            <PremiumCard variant="purple" interactive={false} padding="compact">
              <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
                {[
                  ["Savings", healthComp.savings_points, 30],
                  ["Security", healthComp.anomaly_points, 20],
                  ["Expense Ratio", healthComp.expense_points, 25],
                  ["Consistency", healthComp.consistency_points, 15],
                ].map(([label, val, max]) => (
                  <div key={String(label)} className="text-center">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-500">
                      {label}
                    </p>
                    <p className="mt-1.5 text-xl font-bold tabular-nums text-white">
                      {Math.round((Number(val || 0) / Number(max || 1)) * 100)}%
                    </p>
                    <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-white/[0.06]">
                      <div
                        className="h-full rounded-full bg-gradient-to-r from-purple-500 to-fuchsia-400"
                        style={{ width: `${Math.round((Number(val || 0) / Number(max || 1)) * 100)}%` }}
                      />
                    </div>
                    <p className="mt-1 text-[10px] text-gray-600">
                      {Number(val || 0).toFixed(0)}/{max}
                    </p>
                  </div>
                ))}
              </div>
            </PremiumCard>
          ) : null}
        </div>
      </section>

      {/* Quick action cards */}
      <div className="mt-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <QuickActionCard
          variant="emerald"
          icon={Shield}
          title="FraudShield"
          status={`${intel.fraudPending} pending alerts`}
          badge={intel.fraudPending > 0 ? intel.fraudPending : undefined}
          onClick={() => setActiveTab?.("fraud")}
          delay={0}
        />
        <QuickActionCard
          variant="purple"
          icon={Sparkles}
          title="Subscriptions AI"
          status={intel.monthlyWaste > 0 ? `${apiUtils.formatINR(intel.monthlyWaste)} wasted/mo` : "No obvious waste"}
          onClick={() => setActiveTab?.("subscriptions")}
          delay={reduce ? 0 : 0.06}
        />
        <QuickActionCard
          variant="amber"
          icon={Landmark}
          title="Dark Patterns"
          status={`${intel.darkCount} caught this month`}
          onClick={() => setActiveTab?.("dark-patterns")}
          delay={reduce ? 0 : 0.12}
        />
        <QuickActionCard
          variant="cyan"
          icon={Receipt}
          title="EMI Tracker"
          status={`${intel.emiCount} active EMIs tracked`}
          onClick={() => setActiveTab?.("emi")}
          delay={reduce ? 0 : 0.18}
        />
      </div>

      {/* Row 3 — Spending story */}
      <motion.section
        ref={row3Ref}
        className="mt-8 grid grid-cols-1 gap-4 lg:grid-cols-12 lg:gap-6"
        {...fadeIn}
        transition={{ duration: reduce ? 0.15 : 0.5, ease: [0.22, 1, 0.36, 1], delay: reduce || !r3 ? 0 : 0 }}
      >
        <div className="lg:col-span-7">
          <MonthlyTrendChart trendsData={trends} animateOnView={Boolean(r3 || reduce)} />
        </div>
        <div className="lg:col-span-5">
          <SpendingPieChart
            spendingData={spending}
            month={month}
            year={year}
            prevMonthExpense={prevMonthExpense}
            animateOnView={Boolean(r3 || reduce)}
          />
        </div>
      </motion.section>

      {/* Row 4 — Footer */}
      <footer className="mt-10 flex flex-wrap items-center justify-between gap-3 border-t border-white/[0.06] pt-4 text-[11px] text-exiqo-glow/55">
        <button
          type="button"
          onClick={() => onDataRefresh()}
          className="inline-flex min-h-[48px] items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-3 py-2 text-xs font-medium text-exiqo-glow/90 transition hover:bg-white/[0.08] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60 md:min-h-0"
        >
          <RefreshCw className="h-3.5 w-3.5" aria-hidden />
          Last refreshed {Math.max(1, Math.round((Date.now() - lastRefresh.getTime()) / 60000))} min ago · Tap to refresh
        </button>
        <div className="flex flex-wrap items-center gap-3">
          <span className="tabular-nums opacity-80">build {process.env.REACT_APP_BUILD || "dev"}</span>
          <span className="inline-flex items-center gap-1 text-exiqo-glow/70">
            <BadgeCheck className="h-3.5 w-3.5 text-emerald-400/90" aria-hidden />
            AA-ready
          </span>
          <span className="inline-flex items-center gap-1 text-exiqo-glow/70">
            <Shield className="h-3.5 w-3.5 text-exiqo-purple" aria-hidden />
            DPDP-aware
          </span>
        </div>
      </footer>
    </motion.main>
  );
}
