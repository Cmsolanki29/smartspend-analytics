/**
 * LiveTransactionTicker — Top-bar capsule pill showing the most recent
 * transaction with a live-dot, direction indicator, formatted amount, and
 * merchant name.
 *
 * Visibility: xl (≥1280px) only so it never competes with the search bar on
 * 1024–1279px laptops.
 *
 * Dimensions: h-10 (40px) to share the exact baseline with the search bar.
 * Border-radius: rounded-xl to match search bar for visual harmony.
 *
 * Data: useTickerDemo (Option C) — rotates real DB transactions every 3.5 s.
 * Upgrade to WebSocket/SSE by swapping the hook with no component changes.
 */
import React, { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useTickerDemo } from "../../hooks/useTickerDemo";

// ── Amount formatter ──────────────────────────────────────────────────────────
function formatAmount(amount) {
  if (amount >= 100_000) return (amount / 100_000).toFixed(1) + "L";
  if (amount >= 1_000)   return (amount / 1_000).toFixed(1) + "k";
  return Number(amount).toLocaleString("en-IN");
}

// ── Component ─────────────────────────────────────────────────────────────────
export default function LiveTransactionTicker({ userId, onTabChange }) {
  const { transaction, loading, error } = useTickerDemo(userId);

  // Brief border flash when a new transaction arrives
  const [flash, setFlash] = useState(null); // "credit" | "debit" | null

  useEffect(() => {
    if (!transaction) return;
    const kind = transaction.type === "CREDIT" ? "credit" : "debit";
    setFlash(kind);
    const id = setTimeout(() => setFlash(null), 600);
    return () => clearTimeout(id);
  }, [transaction?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const isCredit = transaction?.type === "CREDIT";

  const borderColor =
    flash === "credit"
      ? "border-emerald-400/40"
      : flash === "debit"
      ? "border-rose-400/40"
      : "border-white/[0.08]";

  return (
    <button
      type="button"
      onClick={() => onTabChange?.("transactions")}
      title="Live transactions · Click to view all"
      aria-label="Live transaction ticker. Click to view all transactions."
      aria-live="polite"
      className={[
        // Show on ≥1024px — search bar truncation is already locked via whitespace-nowrap
        "hidden lg:flex items-center gap-2.5",
        // Fixed sizing — exact match with search bar height
        "h-10 w-[240px] flex-shrink-0 overflow-hidden",
        "px-3.5",
        // rounded-xl matches the search bar's corner radius
        "rounded-xl",
        // Surface
        "bg-white/[0.03]",
        "border transition-colors duration-300",
        borderColor,
        // Interaction
        "cursor-pointer",
        "hover:bg-white/[0.05] hover:border-white/[0.15]",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400/50",
        // Subtle glow matching the search bar's hover glow
        "shadow-[0_0_20px_-8px_rgba(139,92,246,0.15)]",
      ].join(" ")}
    >
      {/* ── LIVE dot + label ─────────────────────────────────────────────── */}
      <div className="flex flex-shrink-0 items-center gap-1.5">
        <span className="relative flex h-1.5 w-1.5 flex-shrink-0" aria-hidden>
          {!error ? (
            <>
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-400" />
            </>
          ) : (
            <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-gray-500" />
          )}
        </span>
        <span className="text-[10px] font-semibold uppercase tracking-[0.10em] text-emerald-300">
          Live
        </span>
      </div>

      {/* ── Divider ──────────────────────────────────────────────────────── */}
      <div className="h-3.5 w-px flex-shrink-0 bg-white/10" aria-hidden />

      {/* ── Animated transaction content ─────────────────────────────────── */}
      <div className="flex min-w-0 flex-1 items-center overflow-hidden">
        {loading ? (
          <span
            className="block h-3 w-28 animate-pulse rounded bg-white/[0.08]"
            aria-hidden
          />
        ) : error ? (
          <span className="text-[11px] text-gray-500">Live feed syncing…</span>
        ) : !transaction ? (
          <span className="text-[11px] text-gray-500">No recent activity</span>
        ) : (
          <AnimatePresence mode="wait">
            <motion.div
              key={transaction.id}
              initial={{ y: 8, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              exit={{ y: -8, opacity: 0 }}
              transition={{ duration: 0.3, ease: "easeOut" }}
              className="flex min-w-0 items-center gap-1.5"
            >
              {/* Direction + amount — shrink-0 so it never clips */}
              <span
                className={[
                  "flex-shrink-0 text-sm font-semibold tabular-nums",
                  isCredit ? "text-emerald-300" : "text-rose-300",
                ].join(" ")}
              >
                {/* Unicode minus − (U+2212) for debits — visually wider than hyphen */}
                {isCredit ? "+" : "−"}₹{formatAmount(transaction.amount)}
              </span>

              {/* Dot separator */}
              <span className="flex-shrink-0 text-xs text-white/20">·</span>

              {/* Merchant — fills remaining space, truncates with ellipsis */}
              <span className="min-w-0 flex-1 truncate text-xs text-gray-400">
                {transaction.merchant}
              </span>
            </motion.div>
          </AnimatePresence>
        )}
      </div>
    </button>
  );
}
