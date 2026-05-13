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
import {
  apiUtils,
  getDarkPatterns,
  getEmiReport,
  getFestivals,
  getFraudShieldAlerts,
  getHealthNarrative,
  getSubscriptions,
} from "../../services/api";
import HealthScoreGauge from "../Charts/HealthScoreGauge";
import MonthlyTrendChart from "../Charts/MonthlyTrendChart";
import SpendingPieChart from "../Charts/SpendingPieChart";
import { ErrorCard } from "../common/ErrorCard";
import { GlassCard } from "../intro/GlassCard";
import { ShieldMark } from "../intro/ShieldMark";
import { SkeletonStats } from "../common/SkeletonCard";
import GuardianPill from "./shared/GuardianPill";
import { KPITile } from "./shared/KPITile";
import NerveCentreCard from "./NerveCentreCard";

const monthKey = (y: number, m: number) => `${y}-${String(m).padStart(2, "0")}`;

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
  const { spending, trends, health, loading, error, loadWarnings, refetch } = useSmartSpend(userId, month, year);
  const trendList = useMemo(() => (Array.isArray(trends) ? trends : []) as TrendPoint[], [trends]);

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

  const row3Ref = useRef<HTMLElement | null>(null);
  const r3 = useInView(row3Ref, { once: true, amount: 0.2 });

  const onDataRefresh = useCallback(async () => {
    await refetch();
    setLastRefresh(new Date());
  }, [refetch]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
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

        if (!cancelled) {
          setIntel({ loading: false, fraudPending: pending, monthlyWaste: waste, nextFest: nf, darkCount, emiCount });
        }
      } catch {
        if (!cancelled) {
          setIntel({ loading: false, fraudPending: 0, monthlyWaste: 0, nextFest: null, darkCount: 0, emiCount: 0 });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [userId]);

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

  const displayName = (userName || "there").trim() || "there";

  const greeting = useMemo(() => {
    const hour = new Date().getHours();
    if (hour < 12) return "Good morning";
    if (hour < 17) return "Good afternoon";
    return "Good evening";
  }, []);

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
    const fromTrend = Number(trendRow?.expense || 0);
    if (fromTrend > 0) return fromTrend;
    return (Array.isArray(spending) ? spending : []).reduce((acc: number, row: { total_amount?: number }) => acc + Number(row.total_amount || 0), 0);
  }, [trendRow, spending]);

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

  const festSub =
    intel.nextFest != null
      ? `${intel.nextFest.name} is in ${intel.nextFest.days_remaining} days`
      : "Your money is calm today.";

  const fadeIn = { initial: reduce ? false : { opacity: 0, y: 14 }, animate: { opacity: 1, y: 0 } };

  return (
    <motion.main
      className="relative mx-auto max-w-[1600px] px-0 pb-28 pt-1 md:pb-10"
      initial={reduce ? false : { opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: reduce ? 0.15 : 0.4, ease: [0.22, 1, 0.36, 1] }}
    >
      {Array.isArray(loadWarnings) && loadWarnings.length > 0 ? (
        <div
          role="status"
          className="mb-4 rounded-xl border border-amber-400/25 bg-amber-500/10 px-4 py-2.5 text-sm text-amber-50/95"
        >
          <span className="font-semibold text-amber-100">Partial data: </span>
          {loadWarnings.join(" · ")}
        </div>
      ) : null}
      {/* Row 1 — Hero + health */}
      <section className="grid grid-cols-1 gap-4 xl:grid-cols-12 xl:gap-6">
        <div className="space-y-4 xl:col-span-7">
          <div>
            <h1 className="font-heading text-3xl font-bold tracking-tight text-white sm:text-4xl lg:text-[2.75rem] lg:leading-tight">
              {greeting}, {displayName}.
            </h1>
            <p className="mt-2 max-w-xl text-sm text-exiqo-glow/75 sm:text-base">{festSub}</p>
          </div>
          <div className="flex snap-x snap-mandatory gap-3 overflow-x-auto pb-1 [-ms-overflow-style:none] [scrollbar-width:none] sm:grid sm:grid-cols-3 sm:overflow-visible [&::-webkit-scrollbar]:hidden">
            <div className="min-w-[min(100%,280px)] shrink-0 snap-center sm:min-w-0">
              <KPITile
                title="Available balance (MTD)"
                value={apiUtils.formatINR(netMonth)}
                subtitle="Net of credits − debits this month"
                icon={Wallet}
                trendPct={netDeltaPct}
                sparklineValues={sparkExpense}
                delay={0}
              />
            </div>
            <div className="min-w-[min(100%,280px)] shrink-0 snap-center sm:min-w-0">
              <KPITile
                title="This month spend"
                value={apiUtils.formatINR(monthSpend)}
                subtitle={`${month}/${year}`}
                icon={Receipt}
                trendPct={spendDeltaPct}
                sparklineValues={sparkExpense}
                delay={reduce ? 0 : 0.08}
              />
            </div>
            <div className="min-w-[min(100%,280px)] shrink-0 snap-center sm:min-w-0">
              <KPITile
                title="Saved this year"
                value={apiUtils.formatINR(savedYtd)}
                subtitle="Sum of monthly savings in calendar year"
                icon={PiggyBank}
                sparklineValues={savedSpark}
                delay={reduce ? 0 : 0.16}
              />
            </div>
          </div>
        </div>

        <div className="relative xl:col-span-5">
          <motion.div
            className="pointer-events-none absolute right-2 top-4 opacity-[0.08]"
            aria-hidden
            animate={reduce ? undefined : { rotate: 360 }}
            transition={{ duration: 120, repeat: Infinity, ease: "linear" }}
          >
            <ShieldMark stage="complete" size={200} />
          </motion.div>
          <HealthScoreGauge healthData={health ?? {}} narration={healthNarrationLine} variant="hero" />
        </div>
      </section>

      {/* Row 1.5 — Living Budget Nerve Centre */}
      <motion.section
        className="mt-6"
        initial={reduce ? false : { opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: reduce ? 0 : 0.12, duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
      >
        <NerveCentreCard userId={userId} setActiveTab={setActiveTab} />
      </motion.section>

      {/* Row 2 — Guardian strip */}
      <motion.section
        className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4"
        initial={reduce ? false : { opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: reduce ? 0 : 0.2, duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
      >
        <GuardianPill
          label="FraudShield"
          sub={`${intel.fraudPending} pending alerts`}
          icon={Shield}
          glow={intel.fraudPending > 0 ? "rose" : "violet"}
          disabled={intel.loading}
          delay={0}
          onClick={() => setActiveTab?.("fraud")}
        />
        <GuardianPill
          label="Subscriptions"
          sub={intel.monthlyWaste > 0 ? `${apiUtils.formatINR(intel.monthlyWaste)} wasted/mo` : "No obvious waste"}
          icon={Sparkles}
          glow={intel.monthlyWaste > 0 ? "amber" : "cyan"}
          disabled={intel.loading}
          delay={reduce ? 0 : 0.06}
          onClick={() => setActiveTab?.("subscriptions")}
        />
        <GuardianPill
          label="Dark Patterns"
          sub={`${intel.darkCount} caught this month`}
          icon={Landmark}
          glow="violet"
          disabled={intel.loading}
          delay={reduce ? 0 : 0.12}
          onClick={() => setActiveTab?.("dark-patterns")}
        />
        <GuardianPill
          label="EMI Tracker"
          sub={`${intel.emiCount} active EMIs tracked`}
          icon={Receipt}
          glow="cyan"
          disabled={intel.loading}
          delay={reduce ? 0 : 0.18}
          onClick={() => setActiveTab?.("emi")}
        />
      </motion.section>

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
