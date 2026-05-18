import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  Calendar, ChevronDown, Landmark, Search, Settings,
} from "lucide-react";
import { ShieldMark } from "../intro/ShieldMark";
import NotificationsBell from "./NotificationsBell";
import CommandPalette from "./CommandPalette";
import UserMenu from "./UserMenu";
import MonthYearPicker from "./MonthYearPicker";
import LiveTransactionTicker from "./LiveTransactionTicker";

const MONTH_LABELS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

const TopBar = ({
  userName = "User",
  userEmail,
  userId,
  month,
  year,
  onMonthChange,
  onYearChange,
  onTabChange,
  onLogout,
}) => {
  const [periodOpen, setPeriodOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const periodTriggerRef = useRef(null);

  const openPalette  = useCallback(() => setPaletteOpen(true),  []);
  const closePalette = useCallback(() => setPaletteOpen(false), []);
  const closePeriod  = useCallback(() => setPeriodOpen(false),  []);

  // Cmd+K global shortcut (ESC / click-outside are handled inside each component)
  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        openPalette();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [openPalette]);

  const displayName = userName?.trim() || "User";
  const monthLabel = MONTH_LABELS[(Number(month) || 1) - 1] || MONTH_LABELS[0];
  const periodLabel = `${monthLabel} ${year}`;

  return (
    <>
      {/*
       * Top bar layout (left → right):
       *   [mobile brand] [search: flex-1 min-w-0] [ticker: xl only] [right cluster: shrink-0]
       *
       * Key rules that prevent the wrapping / overlap bugs:
       *  • No justify-between — search flex-1 naturally pushes the right cluster to the end
       *  • min-w-0 on the search wrapper is critical: allows flex-1 to shrink below its content size
       *  • truncate + whitespace-nowrap on the search placeholder span prevents word-wrapping
       *  • Ticker only appears at xl (≥1280px) so it never competes with search on laptops
       *  • Every interactive element is exactly h-10 (40px), centering cleanly in the h-16 bar
       */}
      <header className="sticky top-0 z-40 h-16 w-full border-b border-white/[0.06] bg-[#0A0612]/80 backdrop-blur-md">
        <div className="mx-auto flex h-full max-w-screen-2xl items-center gap-3 px-4 lg:px-6">

          {/* Mobile brand mark — hidden on md+ (sidebar shows branding there) */}
          <div className="flex shrink-0 items-center gap-2.5 md:hidden">
            <ShieldMark size={36} stage="complete" />
            <span className="hidden font-heading text-[17px] font-semibold tracking-tight text-white sm:inline">
              SmartSpend
            </span>
          </div>

          {/* Search — flex-1 min-w-0 lets it grow but also shrink without overflowing */}
          <div className="min-w-0 flex-1">
            {/* Desktop: full pill with inline ⌘K badge */}
            <button
              type="button"
              onClick={openPalette}
              aria-label="Open search (Cmd+K)"
              className="group relative hidden h-10 w-full max-w-md items-center gap-2.5 overflow-hidden rounded-xl border border-white/[0.08] bg-white/[0.03] px-3.5 transition-all duration-200 hover:border-white/[0.15] hover:bg-white/[0.05] hover:shadow-[0_0_20px_-8px_rgba(124,58,237,0.3)] focus-visible:border-purple-500/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400/50 lg:inline-flex"
            >
              <Search className="h-4 w-4 shrink-0 text-white/40 transition group-hover:text-violet-400" aria-hidden />
              {/* truncate + whitespace-nowrap: placeholder stays on one line and clips with ellipsis */}
              <span className="min-w-0 flex-1 truncate whitespace-nowrap text-left text-sm text-white/40 transition group-hover:text-white/60">
                Search transactions, alerts, navigate…
              </span>
              <kbd className="ml-1 inline-flex shrink-0 items-center gap-0.5 rounded border border-white/[0.08] bg-white/[0.06] px-1.5 py-0.5 text-[10px] font-medium tracking-tight text-white/35">
                ⌘K
              </kbd>
            </button>

            {/* Mobile: icon-only button */}
            <button
              type="button"
              onClick={openPalette}
              aria-label="Open search"
              className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-white/[0.08] bg-white/[0.03] text-white/60 transition-all duration-200 hover:border-white/[0.15] hover:text-violet-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400/50 lg:hidden"
            >
              <Search className="h-[18px] w-[18px]" aria-hidden />
            </button>
          </div>

          {/* Live ticker — lg+ (≥1024px); search bar wrapping is prevented via truncate/whitespace-nowrap */}
          <LiveTransactionTicker userId={userId} onTabChange={onTabChange} />

          {/* RIGHT cluster — shrink-0 so it's never squished */}
          <div className="flex shrink-0 items-center gap-2">
            {/* Bank linked chip — wide label at 2xl, icon-only at lg–xl */}
            <span
              className="hidden h-10 items-center gap-2 rounded-xl border border-emerald-400/25 bg-emerald-500/10 px-3 text-xs font-medium tracking-wide text-emerald-300 2xl:inline-flex"
              title="Bank linked via Account Aggregator"
            >
              <Landmark className="h-3.5 w-3.5" aria-hidden />
              BANK LINKED
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)]" />
            </span>
            <span
              className="relative hidden h-10 w-10 place-items-center rounded-xl border border-emerald-400/25 bg-emerald-500/10 text-emerald-300 lg:grid 2xl:hidden"
              title="Bank linked"
              aria-label="Bank linked"
            >
              <Landmark className="h-4 w-4" aria-hidden />
              <span className="absolute right-1.5 top-1.5 h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)]" />
            </span>

            {/* Period selector */}
            <button
              ref={periodTriggerRef}
              type="button"
              onClick={() => setPeriodOpen((o) => !o)}
              aria-haspopup="dialog"
              aria-expanded={periodOpen}
              aria-label={`Period: ${periodLabel}. Click to change.`}
              className={`inline-flex h-10 shrink-0 items-center gap-2 rounded-xl border pl-3 pr-2 transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400/50 ${
                periodOpen
                  ? "border-purple-400/50 bg-purple-500/15 shadow-[0_0_20px_-6px_rgba(139,92,246,0.5)]"
                  : "border-white/[0.08] bg-white/[0.03] hover:border-white/[0.15] hover:bg-white/[0.05]"
              }`}
            >
              <Calendar className="h-4 w-4 text-white/55" aria-hidden />
              <span className="hidden text-sm tabular-nums tracking-tight text-white/80 lg:inline">
                {periodLabel}
              </span>
              <ChevronDown
                className={`h-4 w-4 text-white/55 transition-transform duration-200 ${
                  periodOpen ? "rotate-180" : ""
                }`}
                aria-hidden
              />
            </button>

            {/* Notifications */}
            <NotificationsBell userId={userId} />

            {/* Settings */}
            <button
              type="button"
              onClick={() => onTabChange?.("settings")}
              aria-label="Settings"
              title="Open Settings"
              className="hidden h-10 w-10 shrink-0 place-items-center rounded-xl border border-white/[0.08] bg-white/[0.03] text-white/60 transition-all duration-200 hover:border-white/[0.15] hover:bg-white/[0.05] hover:text-violet-300 hover:shadow-[0_0_16px_-6px_rgba(124,58,237,0.4)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400/50 sm:grid"
            >
              <Settings className="h-[18px] w-[18px]" />
            </button>

            {/* User menu — replaces static chip */}
            <UserMenu
              userName={displayName}
              userEmail={userEmail}
              userId={userId}
              onTabChange={onTabChange}
              onLogout={onLogout}
            />
          </div>
        </div>
      </header>

      {/* Command palette */}
      <CommandPalette
        open={paletteOpen}
        onClose={closePalette}
        onTabChange={(tab) => { onTabChange?.(tab); closePalette(); }}
        userId={userId}
      />

      {/* Month/year picker */}
      <MonthYearPicker
        open={periodOpen}
        onClose={closePeriod}
        triggerRef={periodTriggerRef}
        month={month}
        year={year}
        onMonthChange={onMonthChange}
        onYearChange={onYearChange}
      />
    </>
  );
};

export default TopBar;
