import React, { useCallback, useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Activity,
  ArrowRight,
  Calculator,
  Car,
  CheckCircle2,
  CreditCard,
  Home,
  IndianRupee,
  Landmark,
  PartyPopper,
  RefreshCcw,
  Smartphone,
  Sparkles,
  TrendingDown,
  X,
} from "lucide-react";
import { PolarAngleAxis, RadialBar, RadialBarChart, ResponsiveContainer } from "recharts";
import {
  getEmiReport,
  getFinancialState,
  getFestivals,
  getFestivalImportantDays,
  getPurchases,
  postEmiAffordabilityCheck,
  postponePurchaseGoal,
  postPurchasePostponeGoal,
  scanEmi,
} from "../../services/api";
import { ErrorCard } from "../common/ErrorCard";
import { useToast } from "../common/Toast";
import { GlassCard } from "../intro/GlassCard";
import { PageHeader } from "../Dashboard/shared/PageHeader";
import { HeroKpiTile } from "../Dashboard/shared/HeroKpiTile";
import { SectionTitle } from "../Dashboard/shared/SectionTitle";
import { inr } from "../../lib/format";

const ACCENT = "#DC2626";

const DANGER_BADGE = {
  SAFE: { cls: "border-emerald-500/40 bg-emerald-500/15 text-emerald-300", label: "Healthy", sub: "Debt status" },
  WARNING: { cls: "border-amber-500/40 bg-amber-500/15 text-amber-200", label: "Watch", sub: "Debt status" },
  DANGER: { cls: "border-orange-500/40 bg-orange-500/15 text-orange-200", label: "Elevated", sub: "Debt status" },
  CRITICAL: { cls: "border-rose-500/45 bg-rose-500/15 text-rose-200", label: "Critical", sub: "Debt status" },
};

const QUICK_EMI = [
  { label: "Phone", amount: 2500 },
  { label: "Scooty", amount: 4800 },
  { label: "Car", amount: 12000 },
  { label: "Home", amount: 25000 },
  { label: "Laptop", amount: 3500 },
];

function EmiTypeIcon({ type, className }) {
  const t = String(type || "").toUpperCase();
  const cn = className || "h-5 w-5 text-[#A78BFA]";
  if (t.includes("HOME")) return <Home className={cn} aria-hidden />;
  if (t.includes("VEHICLE") || t.includes("CAR")) return <Car className={cn} aria-hidden />;
  if (t.includes("PHONE") || t.includes("GADGET")) return <Smartphone className={cn} aria-hidden />;
  if (t.includes("PERSONAL") || t.includes("LOAN")) return <Landmark className={cn} aria-hidden />;
  return <CreditCard className={cn} aria-hidden />;
}

function dispatchPurchaseGoalsChanged(userId) {
  try {
    window.dispatchEvent(new CustomEvent("smartspend:purchase-goals-changed", { detail: { userId } }));
    window.dispatchEvent(new CustomEvent("smartspend-financial-sync", { detail: { userId } }));
  } catch {
    /* ignore */
  }
}

export default function EMITrapDetector({ userId }) {
  const { showToast } = useToast();
  const [state, setState] = useState({ loading: true, error: "", data: null });
  const [cross, setCross] = useState({ loading: false, err: "", purchases: null, festivals: null, importantDays: null });
  const [newEmi, setNewEmi] = useState("");
  const [scanLoading, setScanLoading] = useState(false);
  const [calcLoading, setCalcLoading] = useState(false);
  const [calcError, setCalcError] = useState("");
  const [preCheck, setPreCheck] = useState(null); // financial engine snapshot for pre-check picture
  const [checkResult, setCheckResult] = useState(null);
  const [dismissSuggestion, setDismissSuggestion] = useState(false);
  const [postponing, setPostponing] = useState(false);
  const [selectedGoalId, setSelectedGoalId] = useState(null);
  const [confirmPlan, setConfirmPlan] = useState(null);
  const [successState, setSuccessState] = useState(null); // {itemName, fromDate, toDate, freedAmount}

  useEffect(() => {
    const s = checkResult?.suggestion;
    if (s?.default_goal_id != null) setSelectedGoalId(s.default_goal_id);
    else if (s?.goal_id != null) setSelectedGoalId(s.goal_id);
    else setSelectedGoalId(null);
    setConfirmPlan(null);
  }, [checkResult]);

  const deferGoals = useMemo(() => {
    const s = checkResult?.suggestion;
    if (!s) return [];
    if (Array.isArray(s.deferrable_goals) && s.deferrable_goals.length) return s.deferrable_goals;
    if (s.goal_id != null) {
      return [
        {
          goal_id: s.goal_id,
          item_name: s.item_name,
          current_target_date: s.current_target_date,
          monthly_target: s.old_monthly_target,
          priority: "MEDIUM",
          postpone_options: s.postpone_options || [],
          generic_postpone_months: s.generic_postpone_months,
          is_last_resort: false,
        },
      ];
    }
    return [];
  }, [checkResult]);

  const selectedEntry = useMemo(() => {
    if (!deferGoals.length) return null;
    const gid = selectedGoalId ?? deferGoals[0]?.goal_id;
    return deferGoals.find((g) => g.goal_id === gid) || deferGoals[0];
  }, [deferGoals, selectedGoalId]);

  const festOptions = useMemo(() => {
    const opts = selectedEntry?.postpone_options;
    if (!Array.isArray(opts)) return [null, null];
    return [opts[0] || null, opts[1] || null];
  }, [selectedEntry]);

  const load = useCallback(async () => {
    setState((p) => ({ ...p, loading: true, error: "" }));
    try {
      const data = await getEmiReport(userId);
      setState({ loading: false, error: "", data });
      setCheckResult(null);
      setDismissSuggestion(false);
    } catch (err) {
      const msg = err?.code === "ECONNABORTED" || err?.message?.includes("timeout")
        ? "Backend is starting up. Please wait a moment and retry."
        : err?.response?.data?.detail || err?.message || "Unable to load EMI Tracker";
      setState({ loading: false, error: msg, data: null });
    }
  }, [userId]);

  const loadCross = useCallback(async () => {
    setCross((c) => ({ ...c, loading: true, err: "" }));
    try {
      const [purchases, fest, days] = await Promise.all([
        getPurchases(userId),
        getFestivals(userId),
        getFestivalImportantDays(userId),
      ]);
      setCross({ loading: false, err: "", purchases, festivals: fest, importantDays: days });
    } catch (e) {
      setCross({ loading: false, err: e.message || "Could not load planner context", purchases: null, festivals: null, importantDays: null });
    }
  }, [userId]);

  useEffect(() => {
    load();
  }, [load]);

  // Load financial engine pre-check snapshot (non-blocking, 8s timeout)
  useEffect(() => {
    if (!userId) return;
    const timer = setTimeout(() => setPreCheck(null), 8000); // silent timeout
    getFinancialState(userId)
      .then((data) => { clearTimeout(timer); setPreCheck(data); })
      .catch(() => { clearTimeout(timer); setPreCheck(null); });
    return () => clearTimeout(timer);
  }, [userId]);

  useEffect(() => {
    if (!userId || state.loading || state.error) return;
    loadCross();
  }, [userId, state.loading, state.error, loadCross]);

  const ratio = Number(state.data?.debt_to_income_ratio || 0);
  const dangerLevel = state.data?.danger_level || "SAFE";
  const badge = DANGER_BADGE[dangerLevel] || DANGER_BADGE.SAFE;
  const monthlyIncome = Number(state.data?.monthly_income || 0);
  const totalBurden = Number(state.data?.total_emi_burden || 0);
  const maxNew = Number(state.data?.max_new_emi_allowed || 0);
  const emis = useMemo(() => state.data?.emis_detected ?? [], [state.data]);
  const userLabel = state.data?.user_name?.trim() || "You";
  const advice = state.data?.ai_advice || "";
  const verdict = state.data?.verdict || "";

  const ratioColor = ratio >= 40 ? "#ef4444" : ratio >= 30 ? "#f59e0b" : "#10b981";
  const gaugeData = useMemo(() => [{ name: "dti", value: Math.min(Math.max(ratio, 0), 100), fill: ratioColor }], [ratio, ratioColor]);

  const runScan = async () => {
    setScanLoading(true);
    try {
      await scanEmi(userId);
      await load();
      await loadCross();
    } finally {
      setScanLoading(false);
    }
  };

  const runCalculate = async () => {
    const n = Number(newEmi);
    if (!Number.isFinite(n) || n <= 0) {
      setCalcError("Please enter a valid EMI amount greater than 0.");
      return;
    }
    setCalcLoading(true);
    setCalcError("");
    setDismissSuggestion(false);
    setSuccessState(null);
    try {
      const res = await postEmiAffordabilityCheck(userId, n);
      setCheckResult(res);
    } catch (err) {
      setCheckResult(null);
      setCalcError(err?.response?.data?.detail || err?.message || "Could not run the impact check. Please try again.");
    } finally {
      setCalcLoading(false);
    }
  };

  const rerunCheckAfterPostpone = useCallback(async () => {
    const n = Number(newEmi);
    if (!Number.isFinite(n) || n <= 0) return;
    try {
      const res = await postEmiAffordabilityCheck(userId, n);
      setCheckResult(res);
    } catch {
      /* keep last result */
    }
  }, [userId, newEmi]);

  const applyConfirmedPlan = async () => {
    if (!confirmPlan) return;
    setPostponing(true);
    const fromDate = selectedEntry?.current_target_date || "";
    try {
      let toDate = "";
      let freedAmount = 0;
      if (confirmPlan.kind === "festival") {
        await postponePurchaseGoal(userId, confirmPlan.goalId, {
          new_target_date: confirmPlan.new_target_date,
          reason: "EMI affordability: shift purchase to festival milestone.",
          festival_key: confirmPlan.festival_key || undefined,
          display_timeline_label: confirmPlan.display_timeline_label || undefined,
        });
        toDate = confirmPlan.new_target_date;
        freedAmount = Number(selectedEntry?.monthly_target || 0) - Number(confirmPlan.projected_monthly_target || 0);
      } else {
        await postPurchasePostponeGoal(userId, confirmPlan.goalId, confirmPlan.postpone_months);
        toDate = selectedEntry?.generic_new_target_date || "";
        freedAmount = selectedEntry?.generic_freed_monthly || 0;
      }
      setConfirmPlan(null);
      setSuccessState({
        itemName: confirmPlan.itemName,
        fromDate,
        toDate,
        freedAmount: Math.max(0, freedAmount),
      });
      dispatchPurchaseGoalsChanged(userId);
      await loadCross();
      await rerunCheckAfterPostpone();
    } catch (e) {
      showToast(e.message || "Could not update goal");
    } finally {
      setPostponing(false);
    }
  };

  const scrollToCalculator = () => {
    document.getElementById("emi-calculator")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const sortedEmis = useMemo(() => {
    return [...emis].sort((a, b) => Number(a.payment_date || 0) - Number(b.payment_date || 0));
  }, [emis]);

  const today = new Date();
  const currentMonthLabel = today.toLocaleDateString("en-IN", { month: "long", year: "numeric" });

  if (state.loading) {
    return (
      <div className="space-y-6">
        <div className="h-10 w-72 animate-pulse rounded-xl bg-white/[0.06]" />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-36 animate-pulse rounded-2xl border border-white/[0.06] bg-[#0c0c18]/80" />
          ))}
        </div>
        <div className="h-64 animate-pulse rounded-2xl border border-white/[0.06] bg-[#0c0c18]/80" />
      </div>
    );
  }

  if (state.error) {
    return (
      <div className="rounded-2xl border border-white/10 bg-[#0c0c18]/90 p-6">
        <ErrorCard message={state.error} onRetry={load} />
      </div>
    );
  }

  const suggestion = checkResult?.suggestion;
  const showSuggestionCard = checkResult && !checkResult.affordable && suggestion && !dismissSuggestion;
  const showDismissed = checkResult && !checkResult.affordable && dismissSuggestion;

  return (
    <div className="space-y-8 pb-8">
      {cross.err ? (
        <div className="rounded-xl border border-amber-500/25 bg-amber-500/5 px-4 py-2 text-xs text-amber-100/90">
          Planner link data: {cross.err}
        </div>
      ) : null}

      <PageHeader
        eyebrow="EMI TRACKER"
        title="Your debt health monitor"
        subtitle={`Track EMIs and loan-like debits for ${userLabel}. Cross-linked with Purchase Planner and festival dates for smarter capacity checks.`}
        accentHex={ACCENT}
        rightSlot={
          <div className={`rounded-2xl border px-4 py-3 text-center ${badge.cls}`}>
            <Activity className="mx-auto mb-1 h-6 w-6 opacity-90" aria-hidden />
            <p className="font-heading text-lg font-bold tracking-tight">{badge.label}</p>
            <p className="text-[11px] text-white/50">{badge.sub}</p>
          </div>
        }
      />

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={runScan}
          disabled={scanLoading}
          className="inline-flex min-h-[48px] items-center gap-2 rounded-xl border border-white/15 bg-white/[0.05] px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-white/[0.09] disabled:opacity-50 md:min-h-0"
        >
          <RefreshCcw className={`h-4 w-4 ${scanLoading ? "animate-spin" : ""}`} aria-hidden />
          {scanLoading ? "Rescanning…" : "Rescan transactions"}
        </button>
        <button
          type="button"
          onClick={scrollToCalculator}
          className="inline-flex min-h-[48px] items-center gap-2 rounded-xl bg-gradient-to-r from-exiqo-purple to-exiqo-pink px-5 py-2.5 text-sm font-semibold text-white shadow-ss-cta transition hover:shadow-ss-cta-hover md:min-h-0"
        >
          <Calculator className="h-4 w-4" aria-hidden />
          Can I take one more EMI?
        </button>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <HeroKpiTile label="Monthly EMI burden" value={inr(totalBurden)} caption="Committed outflow (detected)" accentHex={ACCENT} />
        <GlassCard surface="panel" padding="sm" className="rounded-2xl border border-white/10 bg-white/5 backdrop-blur-2xl">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-exiqo-glow/55">Debt-to-income</p>
          <p className="mt-1 font-heading text-3xl font-bold tabular-nums" style={{ color: ratioColor }}>
            {ratio.toFixed(1)}%
          </p>
          <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/[0.06]">
            <motion.div
              className="h-full rounded-full"
              style={{ backgroundColor: ratioColor }}
              initial={{ width: 0 }}
              animate={{ width: `${Math.min(ratio, 100)}%` }}
              transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
            />
          </div>
          <p className="mt-2 text-xs text-exiqo-glow/55">Guideline: keep EMIs under ~30% of income</p>
        </GlassCard>
        <HeroKpiTile
          label="Active EMIs"
          value={String(emis.length)}
          caption={emis.length ? "From last 6 months of debits" : "No recurring pattern yet"}
          accentHex={ACCENT}
        />
        <HeroKpiTile
          label="Safe new EMI headroom"
          value={maxNew > 0 ? inr(maxNew) : "—"}
          caption={maxNew > 0 ? "RBI-style 30% line (from report)" : "At or above guideline"}
          accentHex={ACCENT}
        />
      </div>

      <GlassCard surface="panel" padding="md" className="rounded-2xl border border-white/10 bg-white/5 backdrop-blur-2xl">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-exiqo-purple to-[#3B82F6] text-white shadow-lg">
            <Sparkles className="h-6 w-6" aria-hidden />
          </div>
          <div className="min-w-0 flex-1 space-y-3">
            <p className="text-xs font-semibold uppercase tracking-wider text-exiqo-glow">AI debt advisor</p>
            {verdict ? <p className="text-sm font-medium text-white/90">{verdict}</p> : null}
            <p className="text-sm leading-relaxed text-exiqo-glow/80">{advice}</p>
          </div>
        </div>
      </GlassCard>

      <GlassCard surface="panel" padding="md" className="rounded-2xl border border-white/10 bg-white/5 backdrop-blur-2xl">
        <div className="mb-6 flex flex-col gap-3 border-b border-white/[0.06] pb-4 sm:flex-row sm:items-center sm:justify-between">
          <SectionTitle eyebrow="Detected" title="Active EMIs & loans" />
          <p className="text-xs text-exiqo-glow/55">Auto-detected from recurring debit patterns</p>
        </div>
        {emis.length === 0 ? (
          <div className="py-14 text-center">
            <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-emerald-500/15 text-emerald-400">
              <CheckCircle2 className="h-9 w-9" aria-hidden />
            </div>
            <p className="font-heading text-lg font-semibold text-white">No EMIs detected</p>
            <p className="mx-auto mt-2 max-w-md text-sm text-exiqo-glow/60">
              No strong recurring loan pattern in the last six months — try Rescan after new bank data syncs.
            </p>
          </div>
        ) : (
          <ul className="space-y-3">
            {emis.map((emi) => (
              <li
                key={emi.merchant}
                className="flex flex-col gap-3 rounded-xl border border-white/[0.08] bg-[#070418]/50 p-4 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="flex min-w-0 items-center gap-3">
                  <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-[#7C3AED]/30 bg-[#7C3AED]/15">
                    <EmiTypeIcon type={emi.emi_type} className="h-6 w-6 text-[#A78BFA]" />
                  </span>
                  <div className="min-w-0">
                    <p className="truncate font-medium text-white">{emi.merchant}</p>
                    <p className="text-xs text-exiqo-glow/55">
                      {emi.emi_type} · typical debit ~day {emi.payment_date} · {emi.months_detected} mo. streak
                    </p>
                  </div>
                </div>
                <div className="text-left sm:text-right">
                  <p className="font-heading text-xl font-bold tabular-nums text-white">
                    {inr(emi.amount)}
                    <span className="text-sm font-normal text-exiqo-glow/50"> /mo</span>
                  </p>
                  <p className="mt-1 inline-block rounded-full border border-[#7C3AED]/30 bg-[#7C3AED]/10 px-2.5 py-0.5 text-[11px] font-medium text-exiqo-glow">
                    Next due ~{emi.next_due || "—"}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </GlassCard>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <GlassCard surface="panel" padding="md" className="rounded-2xl border border-white/10 bg-white/5 backdrop-blur-2xl">
          <h3 className="mb-4 font-heading text-base font-semibold text-white">Debt load meter</h3>
          <div className="relative mx-auto h-[220px] max-w-[280px]">
            <ResponsiveContainer width="100%" height="100%">
              <RadialBarChart cx="50%" cy="50%" innerRadius="68%" outerRadius="100%" data={gaugeData} startAngle={180} endAngle={0}>
                <PolarAngleAxis type="number" domain={[0, 100]} tick={false} />
                <RadialBar dataKey="value" cornerRadius={8} background={{ fill: "rgba(255,255,255,0.06)" }} />
              </RadialBarChart>
            </ResponsiveContainer>
            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-end pb-6 text-center">
              <span className="font-heading text-3xl font-bold tabular-nums" style={{ color: ratioColor }}>
                {ratio.toFixed(1)}%
              </span>
              <span className="text-[11px] text-exiqo-glow/50">of income</span>
            </div>
          </div>
        </GlassCard>

        <GlassCard surface="panel" padding="md" className="rounded-2xl border border-white/10 bg-white/5 backdrop-blur-2xl">
          <h3 className="mb-4 font-heading text-base font-semibold text-white">EMI share of income</h3>
          <div className="space-y-4">
            {emis.length === 0 ? (
              <p className="text-sm text-exiqo-glow/55">No rows to chart yet.</p>
            ) : (
              emis.map((emi) => {
                const pct = monthlyIncome > 0 ? (Number(emi.amount || 0) / monthlyIncome) * 100 : 0;
                return (
                  <div key={emi.merchant}>
                    <div className="mb-1 flex justify-between text-xs">
                      <span className="truncate text-exiqo-glow/70">{emi.merchant}</span>
                      <span className="tabular-nums text-white/90">{pct.toFixed(1)}%</span>
                    </div>
                    <div className="h-2 overflow-hidden rounded-full bg-white/[0.06]">
                      <div className="h-full rounded-full bg-gradient-to-r from-exiqo-purple to-ss-cyan" style={{ width: `${Math.min(pct, 100)}%` }} />
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </GlassCard>
      </div>

      {emis.length > 0 ? (
        <GlassCard surface="panel" padding="md" className="rounded-2xl border border-white/10 bg-white/5 backdrop-blur-2xl">
          <SectionTitle title={`Upcoming debits — ${currentMonthLabel}`} />
          <ul className="mt-4 space-y-2">
            {sortedEmis.map((emi) => {
              const day = Number(emi.payment_date) || 1;
              const isToday = today.getDate() === day;
              const daysLeft = day - today.getDate();
              return (
                <li
                  key={`${emi.merchant}-${day}`}
                  className={`flex items-center justify-between gap-3 rounded-xl border px-3 py-3 ${
                    isToday ? "border-rose-500/35 bg-rose-500/10" : "border-white/[0.06] bg-white/[0.02]"
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <span className="grid h-11 w-11 shrink-0 place-items-center rounded-lg bg-white/[0.06] font-heading text-sm font-bold text-white">
                      {day}
                    </span>
                    <div>
                      <p className="font-medium text-white">{emi.merchant}</p>
                      <p className="text-xs text-exiqo-glow/55">
                        {isToday ? "Typical debit day is today (estimated)" : `~${daysLeft > 0 ? `${daysLeft}d` : "Past"} vs today`}
                      </p>
                    </div>
                  </div>
                  <span className="font-heading text-lg font-semibold tabular-nums text-white">{inr(emi.amount)}</span>
                </li>
              );
            })}
          </ul>
        </GlassCard>
      ) : null}

      {/* Pre-check panel: current financial picture before entering EMI */}
      {preCheck && !checkResult && (
        <div className="rounded-2xl border border-white/[0.08] bg-white/[0.02] backdrop-blur-xl">
          <div className="border-b border-white/[0.06] px-5 py-4">
            <p className="text-[10px] font-semibold uppercase tracking-widest text-exiqo-glow/50">Before you add this EMI</p>
            <p className="font-heading text-base font-bold text-white">Here's your current picture</p>
          </div>
          <div className="grid gap-1 p-4 sm:grid-cols-2">
            {[
              { label: "Monthly income", value: preCheck.income, icon: "💰", positive: true },
              { label: "Existing EMIs", value: preCheck.emi_outgo, icon: "📤", positive: false },
              { label: `Festival reserves`, value: preCheck.festival_reserve, icon: "🎉", positive: false, sub: preCheck.festival_detail?.map(f => f.name).join(", ") || "None in next 90d" },
              { label: "Trip / event reserves", value: preCheck.event_reserve, icon: "✈️", positive: false, sub: preCheck.event_detail?.map(e => e.name).join(", ") || "None in next 6 months" },
              { label: "Purchase plans", value: preCheck.purchase_reserve, icon: "🛍️", positive: false, sub: preCheck.purchase_detail?.map(p => p.name).join(", ") || "None active" },
              { label: "Fixed expenses", value: preCheck.fixed_expenses, icon: "💸", positive: false },
            ].map(({ label, value, icon, positive, sub }) => (
              <div key={label} className="flex items-center justify-between gap-2 rounded-xl px-3 py-2.5">
                <div className="flex items-center gap-2.5 min-w-0">
                  <span className="text-base">{icon}</span>
                  <div className="min-w-0">
                    <p className="truncate text-sm text-white/80">{label}</p>
                    {sub && <p className="truncate text-[10px] text-exiqo-glow/40">{sub}</p>}
                  </div>
                </div>
                <span className={`shrink-0 font-heading text-sm font-bold tabular-nums ${positive ? "text-emerald-300" : "text-white/70"}`}>
                  {positive ? "" : "−"}{inr(value)}
                </span>
              </div>
            ))}
          </div>
          <div className={`mx-4 mb-4 flex items-center justify-between rounded-xl border px-4 py-3 ${
            preCheck.surplus_status === "critical" ? "border-rose-500/30 bg-rose-500/10" :
            preCheck.surplus_status === "warning" ? "border-amber-500/30 bg-amber-500/10" :
            "border-emerald-500/30 bg-emerald-500/10"
          }`}>
            <span className="font-semibold text-white">✅ Available surplus</span>
            <span className={`font-heading text-xl font-bold tabular-nums ${
              preCheck.surplus_status === "critical" ? "text-rose-300" :
              preCheck.surplus_status === "warning" ? "text-amber-300" : "text-emerald-300"
            }`}>{inr(preCheck.surplus)}/mo</span>
          </div>
          {preCheck.surplus > 5000 ? (
            <p className="px-5 pb-4 text-xs text-emerald-300/80">
              ✅ Your surplus looks healthy. Enter an EMI amount below to see the full impact.
            </p>
          ) : (
            <p className="px-5 pb-4 text-xs text-amber-200/80">
              ⚠️ Surplus is tight. Adding a new EMI will leave very little room. Review carefully.
            </p>
          )}
        </div>
      )}

      <GlassCard surface="panel" padding="md" id="emi-calculator" className="rounded-2xl border border-exiqo-purple/20 bg-white/5 backdrop-blur-2xl">
        <SectionTitle
          eyebrow="Simulator"
          title="Can I take one more EMI?"
          actions={<span className="hidden text-xs text-exiqo-glow/50 sm:inline">Deterministic check: RBI headroom + liquidity vs goals</span>}
        />
        <div className="mt-6 grid grid-cols-1 gap-8 md:grid-cols-2">
          <div className="space-y-4">
            <p className="text-xs font-medium text-exiqo-glow/60">Quick amounts</p>
            <div className="flex flex-wrap gap-2">
              {QUICK_EMI.map((q) => (
                <button
                  key={q.label}
                  type="button"
                  onClick={() => { setNewEmi(String(q.amount)); setCalcError(""); }}
                  className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60 ${
                    Number(newEmi) === q.amount ? "border-exiqo-purple bg-exiqo-purple/20 text-white" : "border-white/10 bg-white/[0.04] text-exiqo-glow/80 hover:border-white/20"
                  }`}
                >
                  {q.label} · {inr(q.amount)}
                </button>
              ))}
            </div>
            <label className="block text-sm font-medium text-exiqo-glow/70" htmlFor="new-emi-input-emi">
              New monthly EMI (₹)
            </label>
            <div className="relative">
              <IndianRupee className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-exiqo-glow" aria-hidden />
              <input
                id="new-emi-input-emi"
                type="number"
                min="0"
                value={newEmi}
                onChange={(e) => { setNewEmi(e.target.value); setCalcError(""); }}
                placeholder="e.g. 8500"
                className="w-full rounded-xl border border-white/10 bg-[#070418]/80 py-3.5 pl-12 pr-4 text-lg font-semibold text-white placeholder:text-exiqo-glow/35 focus:border-exiqo-purple/50 focus:outline-none focus:ring-2 focus:ring-exiqo-purple/30"
              />
            </div>
            <button
              type="button"
              onClick={runCalculate}
              disabled={calcLoading}
              aria-label="Calculate impact of new monthly EMI"
              className="flex w-full min-h-[48px] items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-exiqo-purple to-exiqo-pink py-3.5 text-sm font-semibold text-white shadow-ss-cta transition hover:shadow-ss-cta-hover disabled:opacity-50 md:min-h-0"
            >
              {calcLoading ? "Calculating…" : "Calculate impact"}
              <ArrowRight className="h-5 w-5" aria-hidden />
            </button>
          </div>

          <GlassCard
            surface="panel"
            padding="md"
            elevation="raised"
            className="rounded-2xl border border-white/10 bg-[#070418]/70"
            role="region"
            aria-live="polite"
            aria-label="CA-style affordability suggestion"
          >
            {calcLoading ? (
              <div className="space-y-3 py-6">
                <div className="h-6 animate-pulse rounded-lg bg-white/[0.06]" />
                <div className="h-24 animate-pulse rounded-xl bg-white/[0.06]" />
                <p className="text-center text-xs text-exiqo-glow/50">Calculating…</p>
              </div>
            ) : calcError ? (
              <div className="rounded-xl border border-rose-500/40 bg-rose-500/10 px-4 py-4">
                <p className="font-semibold text-rose-200">Check failed</p>
                <p className="mt-1 text-xs text-rose-100/75">{calcError}</p>
                <button
                  type="button"
                  onClick={() => { setCalcError(""); runCalculate(); }}
                  className="mt-3 text-xs text-exiqo-glow/70 underline hover:text-white"
                >
                  Retry
                </button>
              </div>
            ) : successState ? (
              <AnimatePresence>
                <motion.div
                  key="success-card"
                  initial={{ opacity: 0, scale: 0.92, y: 12 }}
                  animate={{ opacity: 1, scale: 1, y: 0 }}
                  transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
                  className="space-y-5 py-2"
                >
                  <div className="flex flex-col items-center gap-3 rounded-2xl border border-emerald-500/40 bg-gradient-to-br from-emerald-500/20 to-emerald-900/10 px-4 py-6 text-center">
                    <motion.div
                      initial={{ scale: 0 }}
                      animate={{ scale: [0, 1.25, 1] }}
                      transition={{ duration: 0.5, delay: 0.1, ease: "easeOut" }}
                      className="flex h-16 w-16 items-center justify-center rounded-full border border-emerald-400/40 bg-emerald-400/20 text-emerald-300"
                    >
                      <PartyPopper className="h-8 w-8" aria-hidden />
                    </motion.div>
                    <div>
                      <p className="font-heading text-xl font-bold text-emerald-100">Goal moved!</p>
                      <p className="mt-1 text-sm text-emerald-100/80">
                        <span className="font-semibold">{successState.itemName}</span> purchase date updated
                      </p>
                    </div>
                    <div className="flex w-full items-center justify-center gap-3 rounded-xl border border-white/10 bg-white/[0.04] px-4 py-3">
                      <div className="text-center">
                        <p className="text-[10px] font-semibold uppercase tracking-wider text-exiqo-glow/50">Was</p>
                        <p className="mt-0.5 font-heading text-base font-bold text-white/80">
                          {successState.fromDate
                            ? new Date(successState.fromDate).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })
                            : "—"}
                        </p>
                      </div>
                      <ArrowRight className="h-5 w-5 shrink-0 text-emerald-400" aria-hidden />
                      <div className="text-center">
                        <p className="text-[10px] font-semibold uppercase tracking-wider text-emerald-400/70">Now</p>
                        <p className="mt-0.5 font-heading text-base font-bold text-emerald-200">
                          {successState.toDate
                            ? new Date(successState.toDate).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })
                            : "—"}
                        </p>
                      </div>
                    </div>
                    {successState.freedAmount > 0 ? (
                      <p className="text-sm text-emerald-100/70">
                        Freed up{" "}
                        <span className="font-bold text-emerald-200">{inr(successState.freedAmount)}/mo</span>{" "}
                        toward this EMI.
                      </p>
                    ) : null}
                  </div>
                  {checkResult?.affordable ? (
                    <motion.div
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: 0.35 }}
                      className="rounded-xl border border-emerald-500/35 bg-emerald-500/10 px-4 py-3 text-center"
                    >
                      <CheckCircle2 className="mx-auto mb-1 h-5 w-5 text-emerald-300" aria-hidden />
                      <p className="text-sm font-semibold text-emerald-100">
                        You can now take this EMI safely!
                      </p>
                      <p className="mt-1 text-xs text-emerald-100/70">
                        Fits RBI headroom ({inr(checkResult.safe_cap_rbi)}) and liquidity floor.
                      </p>
                    </motion.div>
                  ) : null}
                  <button
                    type="button"
                    onClick={() => setSuccessState(null)}
                    className="w-full rounded-xl border border-white/15 bg-white/[0.04] py-2.5 text-xs font-semibold text-exiqo-glow/80 transition hover:bg-white/[0.08]"
                  >
                    Run another check
                  </button>
                </motion.div>
              </AnimatePresence>
            ) : checkResult ? (
              <motion.div initial={{ opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }} className="space-y-4">
                {checkResult.affordable ? (
                  <div className="rounded-xl border border-emerald-500/35 bg-emerald-500/10 px-4 py-4 text-center">
                    <CheckCircle2 className="mx-auto mb-2 h-8 w-8 text-emerald-300" aria-hidden />
                    <p className="font-heading text-lg font-semibold text-emerald-100">Within capacity</p>
                    <p className="mt-2 text-sm text-emerald-100/80">
                      This EMI fits both RBI headroom ({inr(checkResult.safe_cap_rbi)}) and your liquidity floor (
                      {inr(checkResult.liquidity_floor)} left after goals and buffer).
                    </p>
                  </div>
                ) : checkResult && !checkResult.affordable && !dismissSuggestion && !suggestion ? (
                  /* EXHAUSTED STATE — No suggestion available */
                  <div className="space-y-4">
                    <div className="rounded-xl border border-rose-500/40 bg-rose-500/10 px-5 py-5">
                      <p className="font-heading text-lg font-bold text-rose-100">
                        ⚠️ Adding this EMI leaves you {inr(Math.abs(checkResult.shortfall || 0))} short/month
                      </p>
                      <p className="mt-2 text-sm text-rose-100/80">
                        Your budget is fully stretched after all commitments. Here's what's taking up your budget:
                      </p>
                      {preCheck && (
                        <div className="mt-3 space-y-1.5 text-xs">
                          {preCheck.festival_detail?.map(f => (
                            <div key={f.id} className="flex justify-between rounded-lg bg-white/[0.04] px-3 py-1.5">
                              <span className="text-white/70">🎉 {f.name}</span>
                              <span className="text-white/90 font-medium">{inr(f.monthly_target)}/mo reserved</span>
                            </div>
                          ))}
                          {preCheck.event_detail?.map(e => (
                            <div key={e.id} className="flex justify-between rounded-lg bg-white/[0.04] px-3 py-1.5">
                              <span className="text-white/70">✈️ {e.name} {e.status === "postponed" ? "(postponed, still reserved)" : ""}</span>
                              <span className="text-white/90 font-medium">{inr(e.monthly_reserve)}/mo reserved</span>
                            </div>
                          ))}
                          {preCheck.purchase_detail?.map(p => (
                            <div key={p.id} className="flex justify-between rounded-lg bg-white/[0.04] px-3 py-1.5">
                              <span className="text-white/70">🛍️ {p.name}</span>
                              <span className="text-white/90 font-medium">{inr(p.monthly_target)}/mo</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                    <div className="rounded-xl border border-white/10 bg-white/[0.03] px-4 py-4">
                      <p className="mb-3 text-xs font-semibold text-exiqo-glow/60">You have 2 options:</p>
                      <div className="space-y-2">
                        <button type="button" onClick={() => setCheckResult(null)} className="w-full rounded-xl border border-white/15 bg-white/[0.04] px-4 py-3 text-left text-sm transition hover:bg-white/[0.07]">
                          <p className="font-semibold text-white">Option A — Wait, skip this EMI for now</p>
                          <p className="mt-0.5 text-xs text-exiqo-glow/60">Your plans are protected. Try again when income improves.</p>
                        </button>
                        <button type="button" onClick={() => setDismissSuggestion(false)} className="w-full rounded-xl border border-amber-500/30 bg-amber-500/8 px-4 py-3 text-left text-sm transition hover:bg-amber-500/15">
                          <p className="font-semibold text-amber-200">Option B — Review your plans</p>
                          <p className="mt-0.5 text-xs text-amber-100/60">Go to Purchase Planner to postpone a goal and free up budget.</p>
                        </button>
                      </div>
                    </div>
                  </div>
                ) : showSuggestionCard ? (
                  <div className="space-y-3">
                    {/* Exhausted state header when shortfall > 0 */}
                    {(checkResult.shortfall || 0) > 0 && (
                      <div className="rounded-xl border border-amber-500/35 bg-amber-900/20 px-4 py-3">
                        <p className="text-sm font-semibold text-amber-100">
                          ⚠️ Adding this EMI leaves you {inr(checkResult.shortfall)}/month short
                        </p>
                        <p className="mt-0.5 text-xs text-amber-100/70">
                          But there's a way to make room — see the plan below:
                        </p>
                      </div>
                    )}
                  <div className="rounded-xl border border-amber-500/40 bg-gradient-to-br from-amber-500/15 to-transparent px-4 py-4">
                    <p className="font-heading text-base font-semibold text-white">
                      {suggestion.primary_title || "You can still take this EMI if you move a purchase plan"}
                    </p>
                    <p className="mt-1 text-sm leading-snug text-exiqo-glow/85">
                      {suggestion.primary_body || suggestion.message}
                    </p>
                    {selectedEntry?.is_last_resort ? (
                      <p className="mt-2 rounded-lg border border-rose-500/30 bg-rose-500/10 px-2 py-1 text-[11px] font-medium text-rose-100/90">
                        Last resort: this touches a HIGH-priority goal — confirm consciously.
                      </p>
                    ) : null}

                    {deferGoals.length > 1 ? (
                      <div className="mt-4 space-y-2">
                        <p className="text-[11px] font-semibold uppercase tracking-wide text-exiqo-glow/55">Pick a goal to move</p>
                        <div className="grid gap-2 sm:grid-cols-2">
                          {deferGoals.map((g) => {
                            const active = (selectedGoalId ?? deferGoals[0]?.goal_id) === g.goal_id;
                            return (
                              <button
                                key={g.goal_id}
                                type="button"
                                onClick={() => {
                                  setSelectedGoalId(g.goal_id);
                                  setConfirmPlan(null);
                                }}
                                className={`rounded-xl border px-3 py-2.5 text-left text-xs transition ${
                                  active ? "border-exiqo-purple bg-exiqo-purple/15 text-white" : "border-white/10 bg-white/[0.03] text-exiqo-glow/80 hover:border-white/20"
                                }`}
                              >
                                <span className="block font-semibold text-white">{g.item_name}</span>
                                <span className="mt-0.5 block text-[11px] text-exiqo-glow/60">
                                  Target {g.current_target_date} · pace {inr(g.monthly_target)}/mo · {g.priority}
                                </span>
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    ) : null}

                    {selectedEntry && !confirmPlan ? (
                      <>
                        <p className="mt-4 text-[11px] font-semibold uppercase tracking-wide text-exiqo-glow/55">Festival milestones (after current target)</p>
                        <div className="mt-2 grid gap-2 sm:grid-cols-2">
                          <button
                            type="button"
                            disabled={!festOptions[0]}
                            onClick={() =>
                              festOptions[0] &&
                              setConfirmPlan({
                                kind: "festival",
                                goalId: selectedEntry.goal_id,
                                itemName: selectedEntry.item_name,
                                new_target_date: festOptions[0].new_target_date,
                                festival_key: festOptions[0].festival_key,
                                display_timeline_label: festOptions[0].display_timeline_label,
                                projected_monthly_target: festOptions[0].projected_monthly_target,
                                labelShort: festOptions[0].label,
                                toastLabel: festOptions[0].display_timeline_label || festOptions[0].label,
                              })
                            }
                            className="min-h-[48px] rounded-xl border border-white/15 bg-white/[0.05] px-3 py-2 text-left text-xs font-semibold text-white transition hover:bg-white/[0.09] disabled:cursor-not-allowed disabled:opacity-40 sm:min-h-0"
                          >
                            {festOptions[0]?.label || "—"}
                          </button>
                          <button
                            type="button"
                            disabled={!festOptions[1]}
                            title={festOptions[1] ? undefined : "No second milestone in range"}
                            onClick={() =>
                              festOptions[1] &&
                              setConfirmPlan({
                                kind: "festival",
                                goalId: selectedEntry.goal_id,
                                itemName: selectedEntry.item_name,
                                new_target_date: festOptions[1].new_target_date,
                                festival_key: festOptions[1].festival_key,
                                display_timeline_label: festOptions[1].display_timeline_label,
                                projected_monthly_target: festOptions[1].projected_monthly_target,
                                labelShort: festOptions[1].label,
                                toastLabel: festOptions[1].display_timeline_label || festOptions[1].label,
                              })
                            }
                            className="min-h-[48px] rounded-xl border border-white/15 bg-white/[0.05] px-3 py-2 text-left text-xs font-semibold text-white transition hover:bg-white/[0.09] disabled:cursor-not-allowed disabled:opacity-40 sm:min-h-0"
                          >
                            {festOptions[1]?.label || "No second milestone"}
                          </button>
                        </div>

                        {selectedEntry.generic_postpone_months != null ? (
                          <button
                            type="button"
                            className="mt-3 w-full rounded-lg border border-dashed border-white/20 py-2 text-center text-[11px] font-medium text-exiqo-glow/75 transition hover:border-white/30 hover:text-white/90"
                            onClick={() =>
                              setConfirmPlan({
                                kind: "generic",
                                goalId: selectedEntry.goal_id,
                                itemName: selectedEntry.item_name,
                                postpone_months: selectedEntry.generic_postpone_months,
                              })
                            }
                          >
                            Or postpone by <span className="font-semibold text-white">{selectedEntry.generic_postpone_months}</span> months
                            (generic)
                          </button>
                        ) : null}
                      </>
                    ) : null}

                    {confirmPlan ? (
                      <div className="mt-4 rounded-xl border border-emerald-500/35 bg-emerald-500/10 px-3 py-3">
                        <p className="text-sm font-semibold text-emerald-50">
                          {confirmPlan.kind === "festival"
                            ? `Apply: ${confirmPlan.itemName} → ${confirmPlan.labelShort}? New pace ${inr(confirmPlan.projected_monthly_target)}/mo`
                            : `Apply: move ${confirmPlan.itemName} by ${confirmPlan.postpone_months} month(s) (generic)?`}
                        </p>
                        <div className="mt-3 flex flex-wrap gap-2">
                          <button
                            type="button"
                            disabled={postponing}
                            onClick={applyConfirmedPlan}
                            className="inline-flex min-h-[44px] flex-1 items-center justify-center gap-2 rounded-xl border border-emerald-500/50 bg-emerald-500/25 px-3 py-2 text-xs font-semibold text-emerald-50 disabled:opacity-50"
                          >
                            <CheckCircle2 className="h-4 w-4" aria-hidden />
                            {postponing ? "Applying…" : "Yes, apply"}
                          </button>
                          <button
                            type="button"
                            disabled={postponing}
                            onClick={() => setConfirmPlan(null)}
                            className="inline-flex min-h-[44px] flex-1 items-center justify-center gap-2 rounded-xl border border-white/15 bg-white/[0.05] px-3 py-2 text-xs font-semibold text-exiqo-glow/80"
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    ) : null}

                    {suggestion.linked_festival ? (
                      <p className="mt-3 inline-flex items-center gap-2 rounded-full border border-ss-cyan/30 bg-ss-cyan/10 px-3 py-1 text-[11px] text-ss-cyan">
                        Linked context: {suggestion.linked_festival.name} · {suggestion.linked_festival.date}
                      </p>
                    ) : null}
                    <ul className="mt-3 max-h-32 list-disc space-y-1 overflow-y-auto pl-4 text-[11px] text-exiqo-glow/70">
                      {(suggestion.rationale_lines || []).slice(0, 8).map((line, i) => (
                        <li key={i}>{line}</li>
                      ))}
                    </ul>
                    <div className="mt-4 grid grid-cols-2 gap-2 text-center text-xs">
                      <div className="rounded-lg border border-white/10 bg-white/[0.04] p-2">
                        <p className="text-exiqo-glow/50">Goal pace (was)</p>
                        <p className="font-heading text-lg font-bold text-white">{inr(suggestion.old_monthly_target)}</p>
                      </div>
                      <div className="rounded-lg border border-white/10 bg-white/[0.04] p-2">
                        <p className="text-exiqo-glow/50">Reference pace (default goal)</p>
                        <p className="font-heading text-lg font-bold text-emerald-200">{inr(suggestion.new_monthly_target)}</p>
                      </div>
                    </div>
                    <p className="mt-2 text-center text-[11px] text-exiqo-glow/60">
                      EMI shortfall modeled: <span className="font-semibold text-amber-200">{inr(checkResult.shortfall)}</span>/mo
                    </p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => setDismissSuggestion(true)}
                        aria-label="Dismiss purchase plan suggestions"
                        className="inline-flex min-h-[44px] flex-1 items-center justify-center gap-2 rounded-xl border border-white/15 bg-white/[0.04] px-4 py-2 text-xs font-semibold text-exiqo-glow/80 transition hover:bg-white/[0.08]"
                      >
                        <X className="h-4 w-4" aria-hidden />
                        Dismiss
                      </button>
                    </div>
                  </div>
                  </div>
                ) : showDismissed ? (
                  <div className="rounded-xl border border-white/15 bg-white/[0.04] px-4 py-4 text-center text-sm text-exiqo-glow/75">
                    Suggestion dismissed — timeline unchanged. Run another check with a different EMI if you like.
                  </div>
                ) : (
                  <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-4 text-sm text-rose-50/90">
                    <p className="font-semibold text-white">Tight on capacity</p>
                    <p className="mt-2 text-xs leading-relaxed">
                      Shortfall vs safe headroom / liquidity: {inr(checkResult.shortfall)}.
                    </p>
                    <ul className="mt-3 list-disc space-y-1 pl-4 text-xs text-exiqo-glow/75">
                      {(checkResult.rationale_lines || []).map((line, i) => (
                        <li key={i}>{line}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </motion.div>
            ) : (
              <div className="space-y-4 py-4 text-center">
                <TrendingDown className="mx-auto h-10 w-10 text-exiqo-glow/40" aria-hidden />
                <p className="text-sm text-exiqo-glow/60">Enter an amount and run the impact check.</p>
                <div className="space-y-2 border-t border-white/[0.06] pt-4 text-left text-sm">
                  <div className="flex justify-between">
                    <span className="text-exiqo-glow/55">RBI new-EMI headroom</span>
                    <span className="font-semibold text-white">{inr(maxNew)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-exiqo-glow/55">Income (basis)</span>
                    <span className="font-semibold text-white">{inr(monthlyIncome)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-exiqo-glow/55">Goals loaded</span>
                    <span className="font-semibold text-white">{cross.purchases?.goals?.length ?? "—"}</span>
                  </div>
                </div>
              </div>
            )}
          </GlassCard>
        </div>
      </GlassCard>
    </div>
  );
}
