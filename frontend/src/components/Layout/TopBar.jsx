import React, { useEffect, useMemo, useRef, useState } from "react";
import { Calendar, ChevronDown, Landmark, Search, Settings, TrendingDown, TrendingUp, ArrowRightLeft } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { GlassCard } from "../intro/GlassCard";
import { ShieldMark } from "../intro/ShieldMark";
import NotificationsBell from "./NotificationsBell";

/** Mock live feed — replace array with a real WebSocket / SSE feed when ready. */
const LIVE_FEED = [
  { id: 1, amount: "₹2,450",  merchant: "Amazon",        type: "debit"    },
  { id: 2, amount: "₹18,000", merchant: "Salary credit",  type: "credit"   },
  { id: 3, amount: "₹649",    merchant: "Netflix",        type: "debit"    },
  { id: 4, amount: "₹5,200",  merchant: "PhonePe UPI",    type: "transfer" },
  { id: 5, amount: "₹340",    merchant: "Swiggy",         type: "debit"    },
  { id: 6, amount: "₹12,000", merchant: "HDFC EMI",       type: "debit"    },
];

const TYPE_ICON = {
  debit:    TrendingDown,
  credit:   TrendingUp,
  transfer: ArrowRightLeft,
};

const TYPE_COLOR = {
  debit:    "text-rose-300/85",
  credit:   "text-emerald-300/85",
  transfer: "text-exiqo-glow/85",
};

function LiveTicker() {
  const [idx, setIdx] = useState(0);

  useEffect(() => {
    const id = window.setInterval(() => setIdx((i) => (i + 1) % LIVE_FEED.length), 4000);
    return () => clearInterval(id);
  }, []);

  const item = LIVE_FEED[idx];
  const Icon = TYPE_ICON[item.type] ?? ArrowRightLeft;
  const color = TYPE_COLOR[item.type] ?? "text-white/70";

  return (
    <div
      className="hidden items-center gap-2 xl:flex h-8 shrink-0 overflow-hidden rounded-full border border-white/10 bg-white/[0.04] px-3"
      aria-live="polite"
      aria-label="Live transaction feed"
    >
      {/* Pulsing dot */}
      <span className="relative flex h-2 w-2 shrink-0" aria-hidden>
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
        <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
      </span>
      <span className="text-[10px] font-semibold uppercase tracking-[0.16em] text-white/40">Live</span>
      <span className="h-3 w-px bg-white/10" aria-hidden />

      {/* Animated transaction */}
      <AnimatePresence mode="wait">
        <motion.span
          key={item.id}
          initial={{ opacity: 0, y: 5 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -5 }}
          transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
          className="flex items-center gap-1.5"
        >
          <Icon className={`h-3 w-3 shrink-0 ${color}`} aria-hidden />
          <span className={`text-[11px] font-semibold tabular-nums ${color}`}>{item.amount}</span>
          <span className="text-[11px] text-white/45">{item.merchant}</span>
        </motion.span>
      </AnimatePresence>
    </div>
  );
}

const MONTH_LABELS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

/**
 * Stub: opens the global Cmd+K command palette. Wire to a real palette later;
 * the TopBar visual must read as a single command surface in the meantime.
 */
const openCommandPalette = () => {
  // TODO: replace with real palette modal (search transactions, alerts, insights, navigation).
  // eslint-disable-next-line no-console
  console.log("[topbar] open command palette");
};

const TopBar = ({ userName = "User", userId, month, year, onMonthChange, onYearChange }) => {
  const [periodOpen, setPeriodOpen] = useState(false);
  const periodRef = useRef(null);

  const yearOptions = useMemo(() => {
    const y = new Date().getFullYear();
    return [y - 2, y - 1, y, y + 1, y + 2];
  }, []);

  useEffect(() => {
    const onClick = (e) => {
      if (periodRef.current && !periodRef.current.contains(e.target)) setPeriodOpen(false);
    };
    const onKey = (e) => {
      if (e.key === "Escape") setPeriodOpen(false);
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        openCommandPalette();
      }
    };
    document.addEventListener("mousedown", onClick);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      window.removeEventListener("keydown", onKey);
    };
  }, []);

  const displayName = userName?.trim() || "User";
  const initial = displayName.charAt(0).toUpperCase() || "U";
  const monthLabel = MONTH_LABELS[(Number(month) || 1) - 1] || MONTH_LABELS[0];
  const periodLabel = `${monthLabel} ${year}`;

  return (
    <header className="sticky top-0 z-40 h-16 w-full border-b border-white/5 bg-ss-bg-deep/95">
      <div className="mx-auto flex h-full max-w-screen-2xl items-center justify-between gap-4 px-4 lg:px-6">
        {/* LEFT — search (with mobile-only brand fallback when sidebar is hidden) */}
        <div className="flex min-w-0 flex-1 items-center gap-3">
          <div className="flex shrink-0 items-center gap-2.5 md:hidden">
            <ShieldMark size={36} stage="complete" />
            <span className="hidden font-heading text-[17px] font-semibold tracking-tight text-white sm:inline">
              SmartSpend
            </span>
          </div>

          {/* Desktop search pill (lg+) */}
          <button
            type="button"
            onClick={openCommandPalette}
            aria-label="Open search (Cmd+K)"
            className="group relative hidden h-10 w-full max-w-[420px] items-center gap-2.5 rounded-full border border-white/10 bg-white/[0.04] px-3.5 transition-all duration-300 ease-brand hover:border-white/20 hover:bg-white/[0.06] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/50 lg:inline-flex"
          >
            <Search className="h-4 w-4 text-white/55 transition group-hover:text-white/80" aria-hidden />
            <span className="flex-1 text-left text-sm text-white/55 transition group-hover:text-white/75">
              Search transactions, alerts, insights…
            </span>
            <kbd className="hidden h-6 items-center gap-1 rounded-md border border-white/10 bg-white/[0.06] px-1.5 text-[11px] font-medium tracking-tight text-white/55 sm:inline-flex">
              ⌘K
            </kbd>
          </button>

          {/* Mobile / tablet search icon (<lg) — opens fullscreen search sheet (TODO) */}
          <button
            type="button"
            onClick={openCommandPalette}
            aria-label="Open search (Cmd+K)"
            className="grid h-10 w-10 shrink-0 place-items-center rounded-full border border-white/10 bg-white/[0.04] text-white/70 transition-all duration-300 ease-brand hover:border-white/20 hover:bg-white/[0.06] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/50 lg:hidden"
          >
            <Search className="h-[18px] w-[18px]" aria-hidden />
          </button>
        </div>

        <LiveTicker />

        {/* RIGHT cluster — single rhythm, all chips h-10, gap-2.5 */}
        <div className="flex shrink-0 items-center gap-2.5">
          {/* Bank chip — full label at xl+, icon + dot at lg, hidden below lg */}
          <span
            className="hidden h-10 items-center gap-2 rounded-full border border-emerald-400/25 bg-emerald-500/10 px-3 text-xs font-medium tracking-wide text-emerald-300 xl:inline-flex"
            title="Bank linked via Account Aggregator"
          >
            <Landmark className="h-3.5 w-3.5" aria-hidden />
            BANK LINKED
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)]" />
          </span>
          <span
            className="relative hidden h-10 w-10 place-items-center rounded-full border border-emerald-400/25 bg-emerald-500/10 text-emerald-300 lg:grid xl:hidden"
            title="Bank linked"
            aria-label="Bank linked"
          >
            <Landmark className="h-4 w-4" aria-hidden />
            <span className="absolute right-1.5 top-1.5 h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)]" />
          </span>

          {/* Period selector — single segmented pill */}
          <div ref={periodRef} className="relative">
            <button
              type="button"
              onClick={() => setPeriodOpen((o) => !o)}
              aria-haspopup="true"
              aria-expanded={periodOpen}
              aria-label={`Period: ${periodLabel}. Click to change.`}
              className="inline-flex h-10 shrink-0 items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] pl-3 pr-2 transition-all duration-300 ease-brand hover:border-white/20 hover:bg-white/[0.06] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/50"
            >
              <Calendar className="h-4 w-4 text-white/55" aria-hidden />
              <span className="hidden text-sm tabular-nums tracking-tight text-white/85 lg:inline">
                {periodLabel}
              </span>
              <ChevronDown
                className={`h-4 w-4 text-white/55 transition-transform duration-300 ease-brand ${
                  periodOpen ? "rotate-180" : ""
                }`}
                aria-hidden
              />
            </button>

            {periodOpen ? (
              <div className="absolute right-0 top-12 z-50 w-[min(20rem,calc(100vw-2rem))]">
                <GlassCard
                  padding="sm"
                  elevation="raised"
                  role="dialog"
                  aria-label="Choose period"
                  className="border-white/10"
                >
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <p className="mb-2 px-1 text-[10px] uppercase tracking-[0.18em] text-white/40">
                        Month
                      </p>
                      <ul className="grid grid-cols-3 gap-1">
                        {MONTH_LABELS.map((m, idx) => {
                          const isCurrent = idx + 1 === Number(month);
                          return (
                            <li key={m}>
                              <button
                                type="button"
                                onClick={() => onMonthChange?.(idx + 1)}
                                aria-pressed={isCurrent}
                                className={`grid h-9 w-full place-items-center rounded-lg text-xs font-medium tracking-tight transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/50 ${
                                  isCurrent
                                    ? "bg-ss-brand text-white shadow-purple-glow"
                                    : "text-white/70 hover:bg-white/[0.06] hover:text-white"
                                }`}
                              >
                                {m}
                              </button>
                            </li>
                          );
                        })}
                      </ul>
                    </div>
                    <div>
                      <p className="mb-2 px-1 text-[10px] uppercase tracking-[0.18em] text-white/40">
                        Year
                      </p>
                      <ul className="space-y-1">
                        {yearOptions.map((y) => {
                          const isCurrent = y === Number(year);
                          return (
                            <li key={y}>
                              <button
                                type="button"
                                onClick={() => onYearChange?.(y)}
                                aria-pressed={isCurrent}
                                className={`flex h-9 w-full items-center justify-center rounded-lg text-sm font-medium tabular-nums tracking-tight transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/50 ${
                                  isCurrent
                                    ? "bg-ss-brand text-white shadow-purple-glow"
                                    : "text-white/70 hover:bg-white/[0.06] hover:text-white"
                                }`}
                              >
                                {y}
                              </button>
                            </li>
                          );
                        })}
                      </ul>
                    </div>
                  </div>
                </GlassCard>
              </div>
            ) : null}
          </div>

          {/* Notifications — live bell with unread badge */}
          <NotificationsBell userId={userId} />

          {/* Settings — hidden on the very narrow phones to keep < 320px layouts intact */}
          <button
            type="button"
            aria-label="Settings"
            className="hidden h-10 w-10 shrink-0 place-items-center rounded-full border border-white/10 bg-white/[0.04] text-white/70 transition-all duration-300 ease-brand hover:border-white/20 hover:bg-white/[0.06] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/50 sm:grid"
          >
            <Settings className="h-[18px] w-[18px]" />
          </button>

          {/* User chip */}
          <button
            type="button"
            aria-label={`Account menu for ${displayName}`}
            className="flex h-10 shrink-0 items-center gap-2.5 rounded-full border border-white/10 bg-white/[0.04] p-1 transition-all duration-300 ease-brand hover:border-white/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/50 md:pr-3"
          >
            <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-ss-brand text-xs font-semibold text-white">
              {initial}
            </span>
            <span className="hidden flex-col items-start leading-tight md:flex">
              <span className="max-w-[8rem] truncate text-[13px] text-white/90">
                {displayName}
              </span>
              <span className="text-[10px] tracking-wide text-ss-cyan">Premium</span>
            </span>
            <ChevronDown className="hidden h-4 w-4 text-white/45 md:block" aria-hidden />
          </button>
        </div>
      </div>
    </header>
  );
};

export default TopBar;
