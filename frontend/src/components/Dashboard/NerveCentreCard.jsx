/**
 * NerveCentreCard — The dashboard "living financial brain" panel.
 * Shows the full monthly surplus breakdown with all commitments.
 * Every plan knows about every other plan.
 */
import React, { useCallback, useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  AlertTriangle,
  ArrowRight,
  Banknote,
  CalendarDays,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  CreditCard,
  Home,
  RefreshCw,
  ShoppingBag,
  Sparkles,
  TrendingDown,
  Wallet,
} from "lucide-react";
import { forceRecalculate, getFinancialState } from "../../services/api";
import { inr } from "../../lib/format";

const STATUS_CONFIG = {
  healthy: {
    label: "Healthy",
    bg: "border-emerald-500/30 bg-emerald-500/10",
    text: "text-emerald-300",
    icon: CheckCircle2,
  },
  warning: {
    label: "Tight",
    bg: "border-amber-500/30 bg-amber-500/10",
    text: "text-amber-300",
    icon: AlertTriangle,
  },
  critical: {
    label: "Critical",
    bg: "border-rose-500/30 bg-rose-500/10",
    text: "text-rose-300",
    icon: TrendingDown,
  },
};

function BudgetRow({ icon: Icon, label, value, sub, highlight = false, negative = false }) {
  return (
    <div className={`flex items-center justify-between gap-2 rounded-xl px-3 py-2.5 ${highlight ? "border border-white/10 bg-white/[0.05]" : ""}`}>
      <div className="flex min-w-0 items-center gap-2.5">
        {Icon && (
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white/[0.06]">
            <Icon className="h-4 w-4 text-exiqo-glow/70" aria-hidden />
          </span>
        )}
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-white/90">{label}</p>
          {sub && <p className="text-[11px] text-exiqo-glow/50">{sub}</p>}
        </div>
      </div>
      <span className={`shrink-0 font-heading text-base font-bold tabular-nums ${negative ? "text-rose-300" : "text-white"}`}>
        {negative ? "−" : ""}{inr(value)}
      </span>
    </div>
  );
}

export default function NerveCentreCard({ userId, setActiveTab }) {
  const [state, setState] = useState({ loading: true, error: "", data: null });
  const [expanded, setExpanded] = useState(false);
  const [recalculating, setRecalculating] = useState(false);

  const load = useCallback(async () => {
    if (!userId) return;
    setState((s) => ({ ...s, loading: true, error: "" }));
    try {
      // Race against 8 second timeout — this panel is non-critical
      const data = await Promise.race([
        getFinancialState(userId),
        new Promise((_, reject) => setTimeout(() => reject(new Error("timeout")), 8000)),
      ]);
      setState({ loading: false, error: "", data });
    } catch (err) {
      setState((s) => ({
        ...s,
        loading: false,
        error: err?.message === "timeout" ? "Budget engine is starting up…" : (err?.message || "Could not load"),
      }));
    }
  }, [userId]);

  useEffect(() => { load(); }, [load]);

  // Re-sync when purchase goals change
  useEffect(() => {
    const handler = () => load();
    window.addEventListener("smartspend:purchase-goals-changed", handler);
    window.addEventListener("smartspend-financial-sync", handler);
    return () => {
      window.removeEventListener("smartspend:purchase-goals-changed", handler);
      window.removeEventListener("smartspend-financial-sync", handler);
    };
  }, [load]);

  const handleRecalculate = async () => {
    setRecalculating(true);
    try {
      const data = await forceRecalculate(userId);
      setState({ loading: false, error: "", data });
    } catch {
      /* keep existing */
    } finally {
      setRecalculating(false);
    }
  };

  if (state.loading) {
    return (
      <div className="rounded-2xl border border-white/[0.08] bg-white/[0.03] p-5">
        <div className="mb-3 h-4 w-40 animate-pulse rounded bg-white/[0.06]" />
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-10 animate-pulse rounded-xl bg-white/[0.04]" />
          ))}
        </div>
      </div>
    );
  }

  if (state.error || !state.data) {
    return (
      <div className="rounded-2xl border border-amber-500/20 bg-amber-500/5 p-4 text-sm text-amber-100/80">
        Could not load budget engine. <button onClick={load} className="underline">Retry</button>
      </div>
    );
  }

  const d = state.data;
  const surplus = Number(d.surplus || 0);
  const status = d.surplus_status || "healthy";
  const sc = STATUS_CONFIG[status] || STATUS_CONFIG.healthy;
  const StatusIcon = sc.icon;

  const purchases = Array.isArray(d.purchase_detail) ? d.purchase_detail : [];
  const festivals = Array.isArray(d.festival_detail) ? d.festival_detail : [];
  const events = Array.isArray(d.event_detail) ? d.event_detail : [];

  return (
    <div className="rounded-2xl border border-white/[0.08] bg-white/[0.02] backdrop-blur-xl">
      {/* Header */}
      <div className="flex items-center justify-between gap-3 border-b border-white/[0.06] px-5 py-4">
        <div className="flex items-center gap-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-exiqo-purple/20 text-exiqo-purple">
            <Sparkles className="h-5 w-5" aria-hidden />
          </span>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-widest text-exiqo-glow/50">Living Budget Engine</p>
            <p className="font-heading text-base font-bold text-white">This month's breakdown</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleRecalculate}
            disabled={recalculating}
            className="rounded-full border border-white/10 p-1.5 text-exiqo-glow/60 transition hover:border-white/20 hover:text-white disabled:opacity-40"
            title="Recalculate"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${recalculating ? "animate-spin" : ""}`} aria-hidden />
          </button>
          <span className={`rounded-xl border px-3 py-1.5 text-xs font-semibold ${sc.bg} ${sc.text}`}>
            <StatusIcon className="mr-1 inline h-3.5 w-3.5" aria-hidden />{sc.label}
          </span>
        </div>
      </div>

      {/* Rows */}
      <div className="space-y-1 p-4">
        <BudgetRow icon={Banknote} label="Monthly income" value={d.income} sub="Your declared income basis" />
        <BudgetRow icon={Home} label="Fixed expenses" value={d.fixed_expenses} sub="Rent, utilities, insurance" negative />
        <BudgetRow icon={CreditCard} label={`EMIs (${d.emi_outgo > 0 ? "detected" : "none yet"})`} value={d.emi_outgo} sub="Active recurring loan debits" negative />

        {festivals.length > 0 && (
          <BudgetRow
            icon={CalendarDays}
            label={`Festival reserves (${festivals.length})`}
            value={d.festival_reserve}
            sub={festivals.map((f) => f.name).join(", ")}
            negative
          />
        )}

        {events.length > 0 && (
          <BudgetRow
            icon={CalendarDays}
            label={`Event reserves (${events.length})`}
            value={d.event_reserve}
            sub={events.map((e) => e.name).join(", ")}
            negative
          />
        )}

        {festivals.length === 0 && events.length === 0 && (
          <div className="flex items-center gap-2 rounded-xl px-3 py-2 text-xs text-exiqo-glow/40">
            <CalendarDays className="h-4 w-4" aria-hidden />
            No festivals/events in next 90 days
          </div>
        )}

        <BudgetRow
          icon={ShoppingBag}
          label={`Purchase goals (${purchases.length})`}
          value={d.purchase_reserve}
          sub={purchases.map((p) => p.name).join(", ")}
          negative
        />

        {/* Divider + Surplus */}
        <div className="border-t border-white/[0.08] pt-2">
          <div className={`flex items-center justify-between rounded-xl border px-4 py-3 ${sc.bg}`}>
            <div className="flex items-center gap-2">
              <Wallet className={`h-5 w-5 ${sc.text}`} aria-hidden />
              <span className="font-semibold text-white">Free surplus / month</span>
            </div>
            <span className={`font-heading text-xl font-bold tabular-nums ${surplus >= 0 ? sc.text : "text-rose-300"}`}>
              {surplus < 0 ? "−" : ""}{inr(Math.abs(surplus))}
            </span>
          </div>

          {surplus < 0 && (
            <motion.div
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              className="mt-2 rounded-xl border border-rose-500/35 bg-rose-500/10 px-3 py-2 text-xs text-rose-100"
            >
              <AlertTriangle className="mr-1.5 inline h-3.5 w-3.5 text-rose-300" aria-hidden />
              Budget is {inr(Math.abs(surplus))} short this month! Open EMI Tracker to free up budget.
            </motion.div>
          )}

          {surplus > 0 && surplus < 5000 && (
            <motion.div
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              className="mt-2 rounded-xl border border-amber-500/30 bg-amber-500/8 px-3 py-2 text-xs text-amber-100/80"
            >
              <AlertTriangle className="mr-1.5 inline h-3.5 w-3.5 text-amber-400" aria-hidden />
              Surplus is tight. Avoid adding new EMIs without reviewing your plans first.
            </motion.div>
          )}
        </div>

        {/* Expandable: active plans */}
        {(purchases.length > 0 || events.length > 0) && (
          <>
            <button
              type="button"
              onClick={() => setExpanded((e) => !e)}
              className="flex w-full items-center justify-center gap-1.5 pt-2 text-[11px] font-medium text-exiqo-glow/55 transition hover:text-white/80"
            >
              {expanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
              {expanded ? "Hide details" : "Show active plans"}
            </button>

            <AnimatePresence>
              {expanded && (
                <motion.div
                  key="details"
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  exit={{ opacity: 0, height: 0 }}
                  transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
                  className="overflow-hidden"
                >
                  <div className="space-y-2 pt-1">
                    {purchases.map((p) => (
                      <div key={p.id} className="flex items-center justify-between rounded-xl border border-white/[0.06] bg-white/[0.02] px-3 py-2 text-xs">
                        <div className="flex items-center gap-2">
                          <ShoppingBag className="h-3.5 w-3.5 text-exiqo-glow/50" aria-hidden />
                          <span className="text-white/80">{p.name}</span>
                          <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-medium ${p.priority === "HIGH" ? "bg-rose-500/15 text-rose-300" : p.priority === "MEDIUM" ? "bg-amber-500/15 text-amber-300" : "bg-emerald-500/15 text-emerald-300"}`}>
                            {p.priority}
                          </span>
                        </div>
                        <span className="tabular-nums text-white/70">{inr(p.monthly_target)}/mo</span>
                      </div>
                    ))}
                    {events.map((e) => (
                      <div key={e.id} className="flex items-center justify-between rounded-xl border border-white/[0.06] bg-white/[0.02] px-3 py-2 text-xs">
                        <div className="flex items-center gap-2">
                          <CalendarDays className="h-3.5 w-3.5 text-exiqo-glow/50" aria-hidden />
                          <span className="text-white/80">{e.name}</span>
                          {e.status === "postponed" && (
                            <span className="rounded-full bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-medium text-amber-300">POSTPONED</span>
                          )}
                        </div>
                        <span className="tabular-nums text-white/70">{inr(e.monthly_reserve)}/mo</span>
                      </div>
                    ))}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </>
        )}

        {/* Quick actions */}
        <div className="mt-1 flex flex-wrap gap-2 pt-1">
          <button
            type="button"
            onClick={() => setActiveTab?.("emi")}
            className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/[0.04] px-3 py-1.5 text-xs font-medium text-exiqo-glow/80 transition hover:bg-white/[0.08]"
          >
            <CreditCard className="h-3.5 w-3.5" aria-hidden /> Add EMI check
            <ArrowRight className="h-3 w-3" aria-hidden />
          </button>
          <button
            type="button"
            onClick={() => setActiveTab?.("purchase")}
            className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/[0.04] px-3 py-1.5 text-xs font-medium text-exiqo-glow/80 transition hover:bg-white/[0.08]"
          >
            <ShoppingBag className="h-3.5 w-3.5" aria-hidden /> Plan purchase
            <ArrowRight className="h-3 w-3" aria-hidden />
          </button>
          <button
            type="button"
            onClick={() => setActiveTab?.("festival")}
            className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/[0.04] px-3 py-1.5 text-xs font-medium text-exiqo-glow/80 transition hover:bg-white/[0.08]"
          >
            <CalendarDays className="h-3.5 w-3.5" aria-hidden /> Festival plan
            <ArrowRight className="h-3 w-3" aria-hidden />
          </button>
        </div>
      </div>
    </div>
  );
}
