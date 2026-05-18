import React, { useMemo, useRef } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { Activity, ArrowRight, ChevronRight, Crown, RefreshCw, Shield } from "lucide-react";
import AlertCards from "./AlertCards";
import MetricCards from "./MetricCards";
import TypologyPanel from "./TypologyPanel";
import TransactionTable from "./TransactionTable";
import { ALERT_CARDS, FLAGGED_TRANSACTIONS, METRICS, TYPOLOGIES } from "./mockData";
import { CHAINVAULT } from "./chainVaultTheme";

type Props = {
  onNavigate?: (tab: string) => void;
};

function formatSyncedAt(d: Date) {
  return d.toLocaleString("en-IN", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZoneName: "short",
  });
}

function IndiaFirstBanner() {
  return (
    <motion.div
      className="relative mb-8 overflow-hidden rounded-2xl border p-5 sm:p-6"
      style={{
        background: "linear-gradient(135deg, rgba(26,22,14,0.98) 0%, rgba(20,18,12,0.98) 50%, rgba(15,14,10,0.98) 100%)",
        borderColor: CHAINVAULT.goldBorder,
        boxShadow: `0 0 48px -12px ${CHAINVAULT.goldGlow}, inset 0 1px 0 rgba(245,215,110,0.08)`,
      }}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
    >
      <motion.div
        className="pointer-events-none absolute -right-16 -top-16 h-48 w-48 rounded-full opacity-30"
        style={{ background: `radial-gradient(circle, ${CHAINVAULT.goldGlow} 0%, transparent 70%)` }}
        aria-hidden
      />
      <div className="relative flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-start gap-4">
          <div
            className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border"
            style={{
              background: "linear-gradient(145deg, rgba(212,175,55,0.2), rgba(154,123,26,0.12))",
              borderColor: CHAINVAULT.goldBorder,
              boxShadow: `0 0 24px ${CHAINVAULT.goldGlow}`,
            }}
          >
            <Shield className="h-6 w-6" style={{ color: CHAINVAULT.goldLight }} strokeWidth={1.75} aria-hidden />
          </div>
          <div className="min-w-0">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <span
                className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.14em]"
                style={{
                  borderColor: CHAINVAULT.goldBorder,
                  background: "rgba(212,175,55,0.12)",
                  color: CHAINVAULT.goldLight,
                }}
              >
                <Crown className="h-3 w-3" aria-hidden />
                India&apos;s first
              </span>
              <span
                className="rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider"
                style={{ background: "rgba(255,255,255,0.06)", color: CHAINVAULT.muted }}
              >
                For end consumers
              </span>
            </div>
            <p className="text-base font-semibold leading-snug text-white sm:text-lg">{CHAINVAULT.indiaHeadline}</p>
            <p className="mt-2 max-w-2xl text-sm leading-relaxed" style={{ color: CHAINVAULT.muted }}>
              {CHAINVAULT.indiaBody}
            </p>
          </div>
        </div>
        <div
          className="shrink-0 self-start rounded-xl border px-4 py-3 text-center sm:self-center"
          style={{
            borderColor: CHAINVAULT.goldBorderSoft,
            background: "rgba(212,175,55,0.06)",
          }}
        >
          <p className="text-[10px] font-semibold uppercase tracking-[0.16em]" style={{ color: CHAINVAULT.muted }}>
            Fraud chains blocked
          </p>
          <p
            className="mt-0.5 font-heading text-2xl font-bold tabular-nums"
            style={{
              background: `linear-gradient(135deg, ${CHAINVAULT.goldLight}, ${CHAINVAULT.gold})`,
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
              backgroundClip: "text",
            }}
          >
            12,400+
          </p>
          <p className="mt-0.5 text-[11px]" style={{ color: CHAINVAULT.muted }}>
            pilot users · India
          </p>
        </div>
      </div>
    </motion.div>
  );
}

export default function ChainVaultPage({ onNavigate }: Props) {
  const reduce = useReducedMotion();
  const tableRef = useRef<HTMLElement>(null);
  const syncedAt = useMemo(() => formatSyncedAt(new Date()), []);
  const alertCount = ALERT_CARDS.length;

  const scrollToTable = () => {
    tableRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <div className="w-full rounded-2xl p-1 font-sans" style={{ background: CHAINVAULT.pageBg }}>
      <IndiaFirstBanner />

      <motion.div
        initial={reduce ? false : { opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
        className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between"
      >
        <div className="min-w-0 flex-1">
          <motion.div
            className="mb-4 h-1 w-14 rounded-full"
            style={{ background: `linear-gradient(90deg, ${CHAINVAULT.goldDark}, ${CHAINVAULT.goldLight})` }}
            aria-hidden
          />
          <p
            className="mb-2 text-[11px] font-semibold uppercase tracking-[0.18em]"
            style={{ color: CHAINVAULT.goldMid }}
          >
            {CHAINVAULT.eyebrow}
          </p>
          <h1
            className="font-heading text-[clamp(1.85rem,3.8vw,2.65rem)] font-semibold leading-tight tracking-tight"
            style={{
              background: `linear-gradient(135deg, #ffffff 25%, ${CHAINVAULT.goldLight} 70%, ${CHAINVAULT.gold})`,
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
              backgroundClip: "text",
            }}
          >
            {CHAINVAULT.name}
          </h1>
          <p className="mt-2 max-w-xl text-[15px] leading-relaxed" style={{ color: CHAINVAULT.muted }}>
            {CHAINVAULT.subtitle}
          </p>
        </div>

        <div className="flex shrink-0 flex-col items-stretch gap-3 sm:items-end">
          <p className="flex items-center gap-2 text-xs" style={{ color: CHAINVAULT.muted }}>
            <RefreshCw className="h-3.5 w-3.5" aria-hidden />
            Last synced {syncedAt}
          </p>
          <div
            className="flex items-center gap-2 self-start rounded-full px-4 py-2 sm:self-end"
            style={{
              background: "rgba(212,175,55,0.08)",
              border: `1px solid ${CHAINVAULT.goldBorderSoft}`,
            }}
          >
            <span className="relative flex h-2 w-2">
              <span
                className="absolute inline-flex h-full w-full animate-ping rounded-full"
                style={{ background: "rgba(52, 211, 153, 0.45)" }}
              />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
            </span>
            <span className="text-sm font-semibold text-white">AI active</span>
            <span className="text-sm" style={{ color: CHAINVAULT.muted }}>
              ·
            </span>
            <span className="text-sm font-semibold tabular-nums text-white">{alertCount} alerts</span>
            <Activity className="h-4 w-4" style={{ color: CHAINVAULT.goldLight }} aria-hidden />
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={scrollToTable}
              className="inline-flex items-center gap-2 rounded-xl border px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-white/[0.04]"
              style={{ borderColor: CHAINVAULT.goldBorder }}
            >
              Review Alerts
              <ArrowRight className="h-4 w-4" aria-hidden />
            </button>
            <button
              type="button"
              onClick={() => onNavigate?.("transactions")}
              className="inline-flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold shadow-[0_0_28px_rgba(212,175,55,0.25)] transition hover:opacity-95"
              style={{
                background: `linear-gradient(135deg, ${CHAINVAULT.goldDark}, ${CHAINVAULT.gold}, ${CHAINVAULT.goldLight})`,
                color: "#1a1408",
              }}
            >
              Transactions
              <ChevronRight className="h-4 w-4" aria-hidden />
            </button>
          </div>
        </div>
      </motion.div>

      <div className="mt-8">
        <AlertCards cards={ALERT_CARDS} onCta={scrollToTable} premium />
      </div>

      <motion.div className="mt-6">
        <MetricCards metrics={METRICS} premium />
      </motion.div>

      <TypologyPanel typologies={TYPOLOGIES} premium />

      <TransactionTable ref={tableRef} rows={FLAGGED_TRANSACTIONS} premium />
    </div>
  );
}
