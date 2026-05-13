import React, { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  AlertTriangle,
  CheckCircle2,
  LayoutGrid,
  Lightbulb,
  RefreshCw,
  TrendingDown,
  Trash2,
  XCircle,
} from "lucide-react";
import { apiUtils, getSubscriptions } from "../../services/api";
import { useToast } from "../common/Toast";
import { EmptyState } from "../common/EmptyState";
import { ErrorCard } from "../common/ErrorCard";
import { PageHeader } from "../Dashboard/shared/PageHeader";
import { HeroKpiTile } from "../Dashboard/shared/HeroKpiTile";
import { inr } from "../../lib/format";

const ACCENT = "#F59E0B";

const tabs = ["ALL", "ACTIVE", "SUSPICIOUS", "DEAD"];

const statToneClass = {
  total: "border-exiqo-purple/35 bg-exiqo-purple/[0.08]",
  active: "border-emerald-500/35 bg-emerald-500/[0.08]",
  suspicious: "border-amber-500/35 bg-amber-500/[0.08]",
  dead: "border-rose-500/35 bg-rose-500/[0.08]",
};

const rowStyle = {
  ACTIVE: {
    border: "border-emerald-500/35 hover:border-emerald-500/50",
    bg: "from-exiqo-dark/70 to-emerald-500/[0.06]",
    icon: CheckCircle2,
    iconClass: "text-emerald-400",
    pill: "bg-emerald-500/15 text-emerald-300 border-emerald-500/25",
  },
  SUSPICIOUS: {
    border: "border-amber-500/35 hover:border-amber-500/50",
    bg: "from-exiqo-dark/70 to-amber-500/[0.06]",
    icon: AlertTriangle,
    iconClass: "text-amber-400",
    pill: "bg-amber-500/15 text-amber-200 border-amber-500/25",
  },
  DEAD: {
    border: "border-rose-500/35 hover:border-rose-500/50",
    bg: "from-exiqo-dark/70 to-rose-500/[0.06]",
    icon: XCircle,
    iconClass: "text-rose-400",
    pill: "bg-rose-500/15 text-rose-200 border-rose-500/25",
  },
};

function lastUsedLabel(days) {
  if (typeof days !== "number") return "—";
  if (days >= 0) return `${days} days ago`;
  return `Recent (${Math.abs(days)}d)`;
}

const SubscriptionGraveyard = ({ userId }) => {
  const { showToast } = useToast();
  const [state, setState] = useState({ loading: true, error: "", data: null });
  const [tab, setTab] = useState("ALL");
  const [modalMerchant, setModalMerchant] = useState("");

  const load = async () => {
    setState((p) => ({ ...p, loading: true, error: "" }));
    try {
      const data = await getSubscriptions(userId);
      setState({ loading: false, error: "", data });
    } catch (err) {
      setState({ loading: false, error: err.message || "Unable to load subscriptions", data: null });
    }
  };

  useEffect(() => {
    load();
  }, [userId]);

  const subs = state.data?.subscriptions || [];
  const visible = useMemo(() => {
    if (tab === "ALL") return subs;
    return subs.filter((s) => s.status === tab);
  }, [subs, tab]);

  const modalGuide = modalMerchant ? state.data?.cancel_guide?.[modalMerchant] : "";

  const monthlyWaste = Number(state.data?.monthly_waste || 0);
  const annualWaste = Number(state.data?.annual_waste || 0);

  if (state.loading) {
    return (
      <div className="space-y-8">
        <div className="h-10 w-56 animate-pulse rounded-lg bg-exiqo-dark/50" />
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 sm:gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-24 animate-pulse rounded-xl border border-exiqo-purple/10 bg-exiqo-dark/35" />
          ))}
        </div>
        <div className="h-24 animate-pulse rounded-xl border border-exiqo-purple/10 bg-exiqo-dark/35" />
      </div>
    );
  }

  if (state.error) {
    return (
      <div className="rounded-2xl border border-exiqo-purple/25 bg-exiqo-dark/40 p-6">
        <ErrorCard message={state.error} onRetry={load} />
      </div>
    );
  }

  const deadCount       = (state.data?.subscriptions || []).filter((s) => s.status === "DEAD").length;
  const suspiciousCount = (state.data?.subscriptions || []).filter((s) => s.status === "SUSPICIOUS").length;
  const activeCount     = (state.data?.subscriptions || []).filter((s) => s.status === "ACTIVE").length;

  return (
    <div className="mx-auto max-w-5xl space-y-8 pb-4">
      <PageHeader
        eyebrow="SUBSCRIPTIONS"
        title="Kill the Waste"
        subtitle="Find forgotten subscriptions and cancel them before they drain your wallet again next month."
        accentHex={ACCENT}
        rightSlot={
          <HeroKpiTile
            label="₹ wasted / year"
            value={inr(annualWaste)}
            caption={`${deadCount} dead · ${suspiciousCount} suspicious · ${activeCount} active`}
            accentHex={ACCENT}
            loading={state.loading}
          />
        }
      />

      {/* Stats — one row on desktop, compact; color only */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 sm:gap-4">
        <div className={`rounded-xl border px-4 py-4 ${statToneClass.total}`}>
          <div className="flex items-start justify-between gap-2">
            <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-white/95">Total</p>
            <LayoutGrid className="h-[18px] w-[18px] shrink-0 text-exiqo-glow" strokeWidth={2.25} aria-hidden />
          </div>
          <p className="mt-1.5 text-2xl font-semibold tabular-nums tracking-tight text-white">
            {state.data?.total_subscriptions ?? 0}
          </p>
        </div>
        <div className={`rounded-xl border px-4 py-4 ${statToneClass.active}`}>
          <div className="flex items-start justify-between gap-2">
            <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-white/95">Active</p>
            <CheckCircle2 className="h-[18px] w-[18px] shrink-0 text-emerald-300" strokeWidth={2.25} aria-hidden />
          </div>
          <p className="mt-1.5 text-2xl font-semibold tabular-nums tracking-tight text-white">
            {state.data?.active_count ?? 0}
          </p>
        </div>
        <div className={`rounded-xl border px-4 py-4 ${statToneClass.suspicious}`}>
          <div className="flex items-start justify-between gap-2">
            <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-white/95">Suspicious</p>
            <AlertTriangle className="h-[18px] w-[18px] shrink-0 text-amber-300" strokeWidth={2.25} aria-hidden />
          </div>
          <p className="mt-1.5 text-2xl font-semibold tabular-nums tracking-tight text-white">
            {state.data?.suspicious_count ?? 0}
          </p>
        </div>
        <div className={`rounded-xl border px-4 py-4 ${statToneClass.dead}`}>
          <div className="flex items-start justify-between gap-2">
            <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-white/95">Dead</p>
            <XCircle className="h-[18px] w-[18px] shrink-0 text-rose-300" strokeWidth={2.25} aria-hidden />
          </div>
          <p className="mt-1.5 text-2xl font-semibold tabular-nums tracking-tight text-white">
            {state.data?.dead_count ?? 0}
          </p>
        </div>
      </div>

      {/* Waste summary */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className={`rounded-xl border p-5 ${
          monthlyWaste <= 0
            ? "border-emerald-500/25 bg-gradient-to-r from-emerald-500/10 to-emerald-500/[0.02]"
            : "border-amber-500/30 bg-gradient-to-r from-amber-500/10 to-transparent"
        }`}
      >
        <div className="flex items-start gap-4 sm:items-center">
          <div
            className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${
              monthlyWaste <= 0 ? "bg-emerald-500/20" : "bg-amber-500/20"
            }`}
          >
            <TrendingDown className={`h-5 w-5 ${monthlyWaste <= 0 ? "text-emerald-400" : "text-amber-400"}`} />
          </div>
          <p className="text-sm font-medium leading-relaxed text-white/90 sm:text-[15px]">
            {monthlyWaste <= 0 ? (
              <>
                <span className="text-emerald-300/95">No material waste</span>
                <span className="text-exiqo-glow/55"> — recurring spend looks aligned with usage.</span>
              </>
            ) : (
              <>
                You are wasting{" "}
                <span className="font-bold text-amber-300">{apiUtils.formatINR(monthlyWaste)}</span>
                <span className="text-exiqo-glow/50">/month</span>
                <span className="text-exiqo-glow/40"> = </span>
                <span className="font-bold text-amber-300">{apiUtils.formatINR(annualWaste)}</span>
                <span className="text-exiqo-glow/50">/year</span>
                <span className="text-exiqo-glow/55"> on subscriptions you barely use.</span>
              </>
            )}
          </p>
        </div>
      </motion.div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2">
        {tabs.map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`rounded-lg px-5 py-2.5 text-sm font-semibold uppercase tracking-wide transition ${
              tab === t
                ? "bg-exiqo-purple text-white shadow-md shadow-exiqo-purple/15"
                : "bg-exiqo-dark/45 text-exiqo-glow/55 hover:bg-exiqo-dark/65 hover:text-exiqo-glow"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {/* List */}
      <div className="space-y-4">
        {visible.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-exiqo-purple/25 bg-exiqo-dark/30 py-20">
            <EmptyState
              icon="📺"
              title="Nothing in this view"
              subtitle={
                subs.length === 0
                  ? "No subscriptions detected for this period."
                  : "Try another filter — nothing matches this tab."
              }
            />
          </div>
        ) : (
          visible.map((s, i) => {
            const cfg = rowStyle[s.status] || rowStyle.ACTIVE;
            const StatusIcon = cfg.icon;
            return (
              <motion.article
                key={s.merchant}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: Math.min(i * 0.04, 0.2) }}
                className={`rounded-2xl border bg-gradient-to-br p-6 transition ${cfg.border} ${cfg.bg}`}
              >
                <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
                  <div className="min-w-0 flex-1">
                    <div className="mb-4 flex flex-wrap items-center gap-3">
                      <StatusIcon className={`h-5 w-5 shrink-0 ${cfg.iconClass}`} />
                      <h2 className="text-xl font-bold tracking-tight text-white">{s.merchant}</h2>
                      <span
                        className={`rounded-full border px-3 py-0.5 text-[11px] font-bold uppercase tracking-wide ${cfg.pill}`}
                      >
                        {s.status}
                      </span>
                    </div>

                    <div className="mb-4 grid gap-4 sm:grid-cols-3">
                      <div>
                        <p className="mb-1 text-xs font-semibold text-exiqo-glow/50">Usage score</p>
                        <p className="text-sm font-semibold tabular-nums text-white">
                          {s.usage_score}
                          <span className="font-normal text-exiqo-glow/45">/100</span>
                        </p>
                      </div>
                      <div>
                        <p className="mb-1 text-xs font-semibold text-exiqo-glow/50">Last used</p>
                        <p className="text-sm font-semibold text-white">{lastUsedLabel(s.last_used_days)}</p>
                      </div>
                      <div>
                        <p className="mb-1 text-xs font-semibold text-exiqo-glow/50">Monthly cost</p>
                        <p className="text-sm font-semibold tabular-nums text-white">{apiUtils.formatINR(s.amount)}</p>
                      </div>
                    </div>

                    {s.insight ? (
                      <p className="max-w-2xl text-sm leading-relaxed text-exiqo-glow/65">{s.insight}</p>
                    ) : null}
                  </div>

                  <div className="flex shrink-0 flex-col items-stretch gap-3 border-t border-white/[0.06] pt-4 lg:w-44 lg:border-0 lg:pt-0 lg:text-right">
                    <div>
                      <p className="text-2xl font-bold tabular-nums tracking-tight text-white">
                        {apiUtils.formatINR(s.amount)}
                      </p>
                      <p className="text-xs text-exiqo-glow/45">per month</p>
                    </div>
                    {s.status === "DEAD" ? (
                      <button
                        type="button"
                        onClick={() => setModalMerchant(s.merchant)}
                        className="rounded-lg border border-rose-500/35 bg-rose-500/10 px-4 py-2 text-sm font-semibold text-rose-200 transition hover:bg-rose-500/15"
                      >
                        Cancel guide
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() =>
                          showToast("Marked for review — cancel from the app when you are ready.")
                        }
                        className="rounded-lg border border-exiqo-purple/40 bg-exiqo-purple/15 px-4 py-2 text-sm font-semibold text-exiqo-glow transition hover:bg-exiqo-purple/25"
                      >
                        Keep / review
                      </button>
                    )}
                  </div>
                </div>
              </motion.article>
            );
          })
        )}
      </div>

      {/* AI */}
      {state.data?.ai_advice ? (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="rounded-2xl border border-orange-500/30 bg-gradient-to-br from-orange-500/10 to-amber-500/[0.04] p-6"
        >
          <div className="flex items-start gap-4">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-orange-500 to-amber-600 shadow-lg">
              <Lightbulb className="h-6 w-6 text-white" />
            </div>
            <div>
              <h3 className="mb-2 text-lg font-bold text-white">AI recommendation</h3>
              <p className="text-sm leading-relaxed text-exiqo-glow/75">{state.data.ai_advice}</p>
            </div>
          </div>
        </motion.div>
      ) : null}

      {modalMerchant ? (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
          onClick={() => setModalMerchant("")}
          role="presentation"
        >
          <div
            className="w-full max-w-md rounded-2xl border border-exiqo-purple/30 bg-exiqo-navy p-6 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="cancel-guide-title"
          >
            <div className="mb-4 flex items-start justify-between gap-3">
              <div className="flex items-center gap-2">
                <Trash2 className="h-5 w-5 text-exiqo-pink" />
                <h3 id="cancel-guide-title" className="text-lg font-semibold text-white">
                  Cancel: {modalMerchant}
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setModalMerchant("")}
                className="rounded-lg px-2 py-1 text-sm text-exiqo-glow/60 hover:bg-white/5 hover:text-white"
              >
                Close
              </button>
            </div>
            <p className="text-sm leading-relaxed text-exiqo-glow/70">
              {modalGuide || "Open subscription settings in the provider app and turn off auto-renew."}
            </p>
          </div>
        </div>
      ) : null}
    </div>
  );
};

export default SubscriptionGraveyard;
