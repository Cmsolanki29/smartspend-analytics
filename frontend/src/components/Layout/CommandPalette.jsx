/**
 * CommandPalette — Premium Cmd+K search palette.
 *
 * Z-INDEX / OPACITY LAYERING (read before touching):
 * ─────────────────────────────────────────────────────────────────────────────
 *  z-40  Backdrop  → fixed inset-0, bg-black/70 backdrop-blur-md
 *                    Dims + blurs the page. Clicking it closes the palette.
 *  z-50  Modal     → bg-[#0B0716]  ← FULLY SOLID. No /XX alpha. No backdrop-blur.
 *                    backdrop-blur on the CONTAINER causes content to bleed
 *                    through even with a high-opacity background. Never add it.
 * ─────────────────────────────────────────────────────────────────────────────
 *  Uses `cmdk` (shouldFilter=false) — we filter manually for dynamic groups.
 *  Fetches real transactions debounced 300 ms.
 *  Stores recent nav items in localStorage.
 */
import React, {
  useCallback, useEffect, useMemo, useRef, useState,
} from "react";
import { createPortal } from "react-dom";
import { Command } from "cmdk";
import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowRightLeft, Brain, Clock, CreditCard,
  EyeOff, LayoutDashboard, Loader2,
  RefreshCw, Search, Settings, ShieldAlert, ShieldCheck,
  ShoppingCart, Sparkles, TrendingDown, TrendingUp,
  X,
} from "lucide-react";
import { getTransactions } from "../../services/api";
import useEscapeKey from "../../hooks/useEscapeKey";

// ─── Navigation catalogue ────────────────────────────────────────────────────
const NAV_ITEMS = [
  { id: "dashboard",     label: "Dashboard",        icon: LayoutDashboard, group: "Workspace",       description: "Financial overview & KPIs"              },
  { id: "transactions",  label: "Transactions",      icon: ArrowRightLeft,  group: "Workspace",       description: "All your transactions & history"        },
  { id: "insights",      label: "AI Insights",       icon: Brain,           group: "AI Intelligence", description: "AI-powered spending patterns"            },
  { id: "subscriptions", label: "Subscriptions AI",  icon: RefreshCw,       group: "AI Intelligence", description: "Detect & manage recurring charges"      },
  { id: "fraud",         label: "FraudShield · 12-Phase", icon: ShieldAlert, group: "AI Intelligence", description: "12-phase AI fraud control room · live APIs" },
  { id: "dark-patterns", label: "Dark Patterns",     icon: EyeOff,          group: "AI Intelligence", description: "Spot predatory pricing & dark UX"       },
  { id: "emi",           label: "EMI Tracker",       icon: CreditCard,      group: "Financial OS",    description: "EMI trap detection & schedule"          },
  { id: "festival",      label: "Festivals & Event Planner", icon: Sparkles, group: "Planning",        description: "Budget for Diwali, Holi & more"         },
  { id: "purchase",      label: "Purchase Planner",  icon: ShoppingCart,    group: "Planning",        description: "Plan large purchases with AI help"      },
  { id: "cybersafe-connect", label: "CyberSafe Connect", icon: ShieldCheck, group: "Risk Awareness", description: "Report fraud to Cybercell · 24hr window" },
  { id: "fraud-shield", label: "ChainVault", icon: ShieldAlert, group: "Risk Awareness", description: "India's first consumer fraud-chain prevention (demo)" },
  { id: "settings",      label: "Settings",          icon: Settings,        group: "System",          description: "App preferences & configuration"        },
];
const GROUP_ORDER = ["Workspace", "AI Intelligence", "Financial OS", "Planning", "Risk Awareness", "System"];

const RECENT_KEY = "ss_cmd_recent";
const MAX_RECENT = 5;

function fmtINR(n) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency", currency: "INR", maximumFractionDigits: 0,
  }).format(Number(n || 0));
}

function getRecent() {
  try { return JSON.parse(localStorage.getItem(RECENT_KEY) || "[]").slice(0, MAX_RECENT); }
  catch { return []; }
}
function pushRecent(id) {
  try {
    const prev = getRecent().filter((r) => r !== id);
    localStorage.setItem(RECENT_KEY, JSON.stringify([id, ...prev].slice(0, MAX_RECENT)));
  } catch { /* ignore */ }
}

// ─── Lock body scroll while palette is open ──────────────────────────────────
function useLockBodyScroll(active) {
  useEffect(() => {
    if (!active) return;
    const original = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = original; };
  }, [active]);
}

// ─── Single result row ────────────────────────────────────────────────────────
function PaletteItem({ item, isRecent, onSelect }) {
  const Icon = item.icon;
  const isTxn = !!item.isTxn;

  return (
    <Command.Item
      value={item.id}
      onSelect={() => onSelect(item)}
      role="option"
      className={[
        // Base
        "group relative flex cursor-pointer select-none items-center gap-3",
        "rounded-lg px-3 py-2.5 outline-none transition-all duration-150",
        // Default text
        "text-gray-300",
        // Active state — cmdk sets data-selected="true" on the focused row
        // bg-[#0B0716] is our base; the gradient sits on top of it via stacking
        "data-[selected=true]:bg-gradient-to-r data-[selected=true]:from-purple-500/15 data-[selected=true]:to-purple-500/5",
        "data-[selected=true]:text-white",
        "hover:bg-white/[0.04]",
      ].join(" ")}
    >
      {/* 2-px left accent bar — visible only when this row is active */}
      <span
        className="absolute left-0 top-2 bottom-2 w-0.5 rounded-full bg-gradient-to-b from-purple-400 to-purple-600 opacity-0 transition-opacity duration-150 group-data-[selected=true]:opacity-100"
        aria-hidden
      />

      {/* Icon box */}
      <span
        className={[
          "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg transition-all duration-150",
          "bg-white/5 group-data-[selected=true]:bg-purple-500/20",
          "group-hover:scale-105",
        ].join(" ")}
      >
        {isTxn ? (
          Number(item.amount) < 0
            ? <TrendingUp  size={16} className="text-emerald-400 group-data-[selected=true]:text-emerald-300" />
            : <TrendingDown size={16} className="text-rose-400 group-data-[selected=true]:text-rose-300" />
        ) : (
          <Icon size={16} className="text-gray-300 transition-colors group-data-[selected=true]:text-purple-300" />
        )}
      </span>

      {/* Text */}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <p className="truncate text-sm font-medium leading-none text-white">
            {item.label}
          </p>
          {isRecent && (
            <Clock size={10} className="shrink-0 text-gray-600" aria-hidden />
          )}
        </div>
        {item.description && (
          <p className="mt-1 truncate text-xs leading-none text-gray-400 group-data-[selected=true]:text-gray-300">
            {item.description}
          </p>
        )}
      </div>

      {/* Amount — transactions only */}
      {isTxn && item.amount != null && (
        <span className="shrink-0 text-sm font-semibold tabular-nums text-gray-300 group-data-[selected=true]:text-white">
          {fmtINR(item.amount)}
        </span>
      )}
    </Command.Item>
  );
}

function GroupLabel({ label }) {
  return (
    <p className="px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.1em] text-gray-500">
      {label}
    </p>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────
const CommandPalette = ({ open, onClose, onTabChange, userId }) => {
  const [query, setQuery]             = useState("");
  const [txns, setTxns]               = useState([]);
  const [txnLoading, setTxnLoading]   = useState(false);
  const [recentIds, setRecentIds]     = useState([]);
  const inputRef = useRef(null);
  const debounce = useRef(null);

  useEscapeKey(open, onClose);
  useLockBodyScroll(open);

  // Reset + focus on open
  useEffect(() => {
    if (open) {
      setQuery("");
      setTxns([]);
      setRecentIds(getRecent());
      setTimeout(() => inputRef.current?.focus(), 40);
    }
  }, [open]);

  // Debounced transaction search
  useEffect(() => {
    clearTimeout(debounce.current);
    if (!query.trim() || query.length < 2) { setTxns([]); return; }

    debounce.current = setTimeout(async () => {
      if (!userId) return;
      setTxnLoading(true);
      try {
        const res  = await getTransactions(userId, { limit: 80 });
        const rows = Array.isArray(res) ? res : (res?.transactions || res?.data || []);
        const q    = query.toLowerCase();
        setTxns(
          rows
            .filter((r) => (r.merchant || r.description || "").toLowerCase().includes(q))
            .slice(0, 6)
            .map((r) => ({
              id:          `txn-${r.id}`,
              isTxn:       true,
              label:       r.merchant || r.description || "Transaction",
              description: `${r.category || "Other"} · ${
                r.date
                  ? new Date(r.date).toLocaleDateString("en-IN", { day: "2-digit", month: "short" })
                  : ""
              }`,
              amount:    r.amount,
              tabTarget: "transactions",
            }))
        );
      } catch { setTxns([]); }
      finally { setTxnLoading(false); }
    }, 300);

    return () => clearTimeout(debounce.current);
  }, [query, userId]);

  const handleSelect = useCallback((item) => {
    pushRecent(item.tabTarget || item.id);
    onTabChange?.(item.tabTarget || item.id);
    onClose();
  }, [onTabChange, onClose]);

  // ── Derived ───────────────────────────────────────────────────────────────
  const q = query.trim().toLowerCase();

  const filteredNav = useMemo(() => {
    if (!q) return NAV_ITEMS;
    return NAV_ITEMS.filter(
      (n) =>
        n.label.toLowerCase().includes(q) ||
        n.description.toLowerCase().includes(q) ||
        n.group.toLowerCase().includes(q)
    );
  }, [q]);

  const groupedNav = useMemo(() => {
    const map = {};
    filteredNav.forEach((item) => {
      if (!map[item.group]) map[item.group] = [];
      map[item.group].push(item);
    });
    return map;
  }, [filteredNav]);

  const recentItems = useMemo(
    () => recentIds.map((id) => NAV_ITEMS.find((n) => n.id === id)).filter(Boolean),
    [recentIds]
  );

  const totalResults = filteredNav.length + txns.length;
  const showEmpty    = q.length >= 2 && totalResults === 0 && !txnLoading;

  return createPortal(
    <AnimatePresence>
      {open && (
        <>
          {/*
           * ── LAYER 1: Backdrop ── z-40
           * bg-black/70 + backdrop-blur-md dims + blurs the page behind.
           * The blur lives HERE, on a separate layer — NOT on the modal itself.
           * This is the only element that should have backdrop-blur.
           */}
          <motion.div
            key="cmd-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            onClick={onClose}
            className="fixed inset-0 z-40 bg-black/70 backdrop-blur-md"
            aria-hidden
          />

          {/*
           * ── LAYER 2: Modal ── z-50
           * bg-[#0B0716] is FULLY SOLID (no /XX alpha).
           * NO backdrop-blur on this element — that would make content bleed through.
           * The solid colour completely blocks what's behind.
           */}
          <motion.div
            key="cmd-modal"
            initial={{ opacity: 0, scale: 0.95, y: -8 }}
            animate={{ opacity: 1, scale: 1,    y:  0 }}
            exit={{    opacity: 0, scale: 0.95, y: -6 }}
            transition={{ type: "spring", stiffness: 500, damping: 32, mass: 0.6 }}
            role="dialog"
            aria-modal="true"
            aria-label="Command palette"
            className={[
              // Positioning — fixed center, ~15vh from top
              "fixed left-1/2 top-[15vh] z-50 -translate-x-1/2",
              // Width — full on mobile, capped at 2xl desktop
              "w-full max-w-2xl mx-4",
              // ✅ SOLID background — the only correct way to block bleed-through
              "bg-[#0B0716]",
              // Border + shape
              "rounded-2xl overflow-hidden",
              "border border-purple-500/20",
              // Soft purple glow drop shadow
              "shadow-[0_20px_70px_-10px_rgba(139,92,246,0.3)]",
            ].join(" ")}
          >
            <Command shouldFilter={false} loop className="flex flex-col">

              {/* ── Search input row ───────────────────────────── */}
              <div className="flex items-center gap-3 border-b border-white/10 px-5 py-4">
                <Search size={20} className="shrink-0 text-gray-400" aria-hidden />
                <Command.Input
                  ref={inputRef}
                  value={query}
                  onValueChange={setQuery}
                  placeholder="Search transactions, alerts, navigate…"
                  className="flex-1 bg-transparent text-base text-white outline-none placeholder:text-gray-500"
                  autoComplete="off"
                  spellCheck={false}
                  aria-label="Search"
                />
                <div className="flex shrink-0 items-center gap-2">
                  {txnLoading && (
                    <Loader2 size={14} className="animate-spin text-gray-600" />
                  )}
                  {query ? (
                    <button
                      type="button"
                      onClick={() => setQuery("")}
                      className="flex h-5 w-5 items-center justify-center rounded text-gray-500 transition-colors hover:text-gray-300"
                      aria-label="Clear search"
                    >
                      <X size={13} />
                    </button>
                  ) : (
                    <kbd className="hidden items-center rounded border border-white/10 bg-white/5 px-2 py-0.5 font-mono text-[11px] text-gray-400 sm:flex">
                      ESC
                    </kbd>
                  )}
                </div>
              </div>

              {/* ── Results ───────────────────────────────────── */}
              <Command.List className="max-h-[420px] overflow-y-auto overscroll-contain p-2 scrollbar-thin scrollbar-track-transparent scrollbar-thumb-white/10">

                {/* Empty state */}
                {showEmpty && (
                  <div
                    className="flex flex-col items-center gap-2 py-12 text-center"
                    role="status"
                  >
                    <Search size={28} className="text-gray-700" aria-hidden />
                    <p className="text-sm text-gray-500">
                      No results for{" "}
                      <span className="text-gray-400">"{query}"</span>
                    </p>
                    <p className="text-xs text-gray-600">
                      Try a merchant name, tab, or category
                    </p>
                  </div>
                )}

                {/* Recent (shown only when input is empty) */}
                {!q && recentItems.length > 0 && (
                  <Command.Group>
                    <GroupLabel label="Recent" />
                    <div className="space-y-0.5">
                      {recentItems.map((item) => (
                        <PaletteItem
                          key={`recent-${item.id}`}
                          item={item}
                          isRecent
                          onSelect={handleSelect}
                        />
                      ))}
                    </div>
                  </Command.Group>
                )}

                {/* Navigation groups */}
                {GROUP_ORDER.map((group) => {
                  const items = groupedNav[group];
                  if (!items?.length) return null;
                  return (
                    <Command.Group key={group}>
                      <GroupLabel label={group} />
                      <div className="space-y-0.5">
                        {items.map((item) => (
                          <PaletteItem
                            key={item.id}
                            item={item}
                            onSelect={handleSelect}
                          />
                        ))}
                      </div>
                    </Command.Group>
                  );
                })}

                {/* Transactions */}
                {txns.length > 0 && (
                  <Command.Group>
                    <GroupLabel label="Transactions" />
                    <div className="space-y-0.5">
                      {txns.map((item) => (
                        <PaletteItem
                          key={item.id}
                          item={item}
                          onSelect={handleSelect}
                        />
                      ))}
                    </div>
                  </Command.Group>
                )}
              </Command.List>

              {/* ── Footer — keyboard hints ────────────────────── */}
              <div className="hidden items-center gap-4 border-t border-white/10 px-4 py-2.5 text-[11px] text-gray-500 sm:flex">
                {[
                  { keys: ["↑", "↓"], label: "navigate" },
                  { keys: ["↵"],      label: "open"      },
                  { keys: ["ESC"],    label: "close"      },
                ].map(({ keys, label }) => (
                  <span key={label} className="flex items-center gap-1.5">
                    {keys.map((k) => (
                      <kbd
                        key={k}
                        className="rounded border border-white/10 bg-white/5 px-1.5 py-0.5 font-mono text-[10px] text-gray-400"
                      >
                        {k}
                      </kbd>
                    ))}
                    <span>{label}</span>
                  </span>
                ))}
                <span className="ml-auto">
                  {totalResults} result{totalResults !== 1 ? "s" : ""}
                </span>
              </div>

            </Command>
          </motion.div>
        </>
      )}
    </AnimatePresence>,
    document.body
  );
};

export default CommandPalette;
