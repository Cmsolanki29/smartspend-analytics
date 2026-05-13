import React, { useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  Activity,
  BarChart3,
  Bell,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  LayoutDashboard,
  LineChart,
  LogOut,
  Menu,
  Receipt,
  Settings,
  Shield,
  ShoppingBag,
  Sparkles,
  X,
} from "lucide-react";
import { ShieldMark } from "../intro/ShieldMark";

/**
 * Single WORKSPACE nav — FraudShield is the only fraud entry point.
 * Order matches product IA (CTO directive May 2026).
 */
const PRIMARY_NAV = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "transactions", label: "Transactions", icon: Receipt },
  { id: "fraud", label: "FraudShield", icon: Shield },
  { id: "insights", label: "Insights", icon: BarChart3 },
  { id: "emi", label: "EMI Tracker", icon: Activity },
  { id: "dark-patterns", label: "Analytics", icon: LineChart },
  { id: "festival", label: "Festivals", icon: Sparkles },
  { id: "purchase", label: "Purchase Planner", icon: ShoppingBag },
  { id: "family-events", label: "Trips & Events", icon: CalendarDays },
  { id: "subscriptions", label: "Subscriptions", icon: Bell },
  { id: "settings", label: "Settings", icon: Settings },
];

const sidebarWidth = (collapsed) => (collapsed ? 80 : 256);

const MOBILE_SHORTCUTS = ["dashboard", "transactions", "fraud", "insights"];

const Sidebar = ({ collapsed, onToggle, activeTab, onTabChange, onLogout, fraudBadgeCount }) => {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const navItems = useMemo(
    () =>
      PRIMARY_NAV.map((item) =>
        item.id === "fraud" && typeof fraudBadgeCount === "number" && fraudBadgeCount > 0
          ? { ...item, badge: fraudBadgeCount }
          : item
      ),
    [fraudBadgeCount]
  );

  const go = (id) => {
    onTabChange(id);
    setMobileMenuOpen(false);
  };

  return (
    <>
      <motion.aside
        initial={false}
        animate={{ width: sidebarWidth(collapsed) }}
        transition={{ type: "spring", stiffness: 280, damping: 34 }}
        className="fixed left-0 top-0 z-50 hidden h-screen flex-col overflow-hidden border-r border-white/10 bg-white/[0.04] shadow-[0_0_60px_rgba(124,58,237,0.08)] backdrop-blur-2xl md:flex"
      >
        <div className="flex h-16 items-center gap-2 border-b border-white/[0.06] px-3">
          {!collapsed ? (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex min-w-0 flex-1 items-center gap-2.5 pl-1"
            >
              <ShieldMark size={36} stage="complete" />
              <span className="truncate font-heading text-[17px] font-semibold tracking-tight text-white">SmartSpend</span>
            </motion.div>
          ) : null}

          <button
            type="button"
            onClick={onToggle}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className={`grid h-10 w-10 shrink-0 place-items-center rounded-full border border-white/10 bg-white/[0.04] text-white/70 transition-all duration-300 ease-brand hover:border-white/20 hover:bg-white/[0.06] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/50 ${
              collapsed ? "mx-auto" : ""
            }`}
          >
            {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto px-2 pb-4">
          <div>
            {!collapsed && (
              <div className="px-4 pb-2 pt-6 text-[10px] uppercase tracking-[0.18em] text-white/40">Workspace</div>
            )}
            {collapsed && <div className="my-3 border-t border-white/[0.06]" />}
            <div className="space-y-1">
              {navItems.map((item) => {
                const Icon = item.icon;
                const isActive = activeTab === item.id;
                return (
                  <motion.button
                    key={item.id}
                    type="button"
                    onClick={() => go(item.id)}
                    whileHover={{ x: 3 }}
                    whileTap={{ scale: 0.98 }}
                    className={`group relative flex w-full min-h-[48px] items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-all duration-500 ease-brand md:min-h-0 ${
                      isActive
                        ? "bg-white/[0.08] text-white shadow-[inset_0_0_0_1px_rgba(255,255,255,0.06)]"
                        : "text-exiqo-glow/70 hover:bg-white/[0.05] hover:text-white"
                    }`}
                  >
                    {isActive ? (
                      <motion.div
                        layoutId="nav-active-bar"
                        className="absolute left-0 top-1/2 h-8 w-1 -translate-y-1/2 rounded-r-full bg-ss-brand shadow-[0_0_16px_rgba(124,58,237,0.55)]"
                        transition={{ type: "spring", stiffness: 500, damping: 34 }}
                      />
                    ) : null}
                    <Icon size={18} className={`${collapsed ? "mx-auto" : ""} shrink-0 ${isActive ? "text-exiqo-glow" : ""}`} />
                    {!collapsed ? <span className="flex-1 truncate text-left text-sm font-medium">{item.label}</span> : null}
                    {!collapsed && item.badge ? (
                      <span className="rounded-md bg-exiqo-pink px-2 py-0.5 text-xs font-bold text-white shadow-pink-glow">{item.badge}</span>
                    ) : null}
                    {collapsed ? (
                      <span className="pointer-events-none absolute left-full z-50 ml-2 whitespace-nowrap rounded-xl border border-white/10 bg-[#0a0e27]/95 px-3 py-2 text-sm text-white opacity-0 shadow-2xl backdrop-blur-xl transition-opacity group-hover:opacity-100">
                        {item.label}
                        {item.badge ? (
                          <span className="ml-2 rounded-md bg-exiqo-pink px-1.5 py-0.5 text-xs text-white">{item.badge}</span>
                        ) : null}
                      </span>
                    ) : null}
                  </motion.button>
                );
              })}
            </div>
          </div>
        </nav>

        <div className="border-t border-white/[0.06] p-2 pb-[max(1rem,env(safe-area-inset-bottom))]">
          <motion.button
            type="button"
            onClick={onLogout}
            whileHover={{ x: 3 }}
            whileTap={{ scale: 0.98 }}
            className="group relative flex w-full min-h-[48px] items-center gap-3 rounded-xl px-3 py-2.5 text-rose-300 transition-all duration-500 ease-brand hover:bg-rose-500/10 hover:text-rose-200 md:min-h-0"
          >
            <LogOut size={18} className={collapsed ? "mx-auto" : ""} />
            {!collapsed ? <span className="text-sm font-medium">Logout</span> : null}
            {collapsed ? (
              <span className="pointer-events-none absolute left-full ml-2 whitespace-nowrap rounded-xl border border-white/10 bg-[#0a0e27]/95 px-3 py-2 text-sm text-white opacity-0 shadow-xl transition-opacity group-hover:opacity-100">
                Logout
              </span>
            ) : null}
          </motion.button>
        </div>
      </motion.aside>

      <nav
        className="fixed bottom-0 left-0 right-0 z-50 flex items-stretch justify-around border-t border-white/10 bg-[#070418]/95 px-1 pt-1 backdrop-blur-2xl md:hidden pb-[max(0.5rem,env(safe-area-inset-bottom))]"
        aria-label="Primary"
      >
        {MOBILE_SHORTCUTS.map((id) => {
          const item = navItems.find((n) => n.id === id);
          if (!item) return null;
          const Icon = item.icon;
          const isActive = activeTab === id;
          return (
            <button
              key={id}
              type="button"
              onClick={() => go(id)}
              className={`flex min-h-[52px] min-w-[56px] flex-1 flex-col items-center justify-center gap-0.5 rounded-xl text-[10px] font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60 ${
                isActive ? "text-white" : "text-exiqo-glow/60"
              }`}
            >
              <span className={`relative flex h-9 w-9 items-center justify-center rounded-xl ${isActive ? "bg-white/[0.1]" : ""}`}>
                {isActive ? (
                  <span className="absolute inset-x-1 -top-0.5 h-0.5 rounded-full bg-ss-brand shadow-[0_0_12px_rgba(124,58,237,0.8)]" />
                ) : null}
                <Icon className="h-5 w-5" aria-hidden />
                {item.badge ? (
                  <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-exiqo-pink px-0.5 text-[9px] font-bold text-white">
                    {item.badge > 9 ? "9+" : item.badge}
                  </span>
                ) : null}
              </span>
              <span className="max-w-[4.5rem] truncate">{item.label.split(" ")[0]}</span>
            </button>
          );
        })}
        <button
          type="button"
          onClick={() => setMobileMenuOpen(true)}
          className="flex min-h-[52px] min-w-[56px] flex-1 flex-col items-center justify-center gap-0.5 rounded-xl text-[10px] font-semibold text-exiqo-glow/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60"
        >
          <span className="flex h-9 w-9 items-center justify-center rounded-xl">
            <Menu className="h-5 w-5" aria-hidden />
          </span>
          More
        </button>
      </nav>

      <AnimatePresence>
        {mobileMenuOpen ? (
          <motion.div className="fixed inset-0 z-[60] md:hidden" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <button type="button" className="absolute inset-0 bg-black/70 backdrop-blur-sm" aria-label="Close menu" onClick={() => setMobileMenuOpen(false)} />
            <motion.div
              initial={{ y: "100%" }}
              animate={{ y: 0 }}
              exit={{ y: "100%" }}
              transition={{ type: "spring", stiffness: 320, damping: 32 }}
              className="absolute bottom-0 left-0 right-0 max-h-[78vh] overflow-y-auto rounded-t-3xl border border-white/10 bg-[#070418] p-4 pb-[max(1.25rem,env(safe-area-inset-bottom))] shadow-2xl"
            >
              <div className="mb-3 flex items-center justify-between">
                <p className="text-sm font-semibold text-white">Navigate</p>
                <button
                  type="button"
                  onClick={() => setMobileMenuOpen(false)}
                  className="rounded-xl p-2 text-exiqo-glow hover:bg-white/[0.06] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60"
                  aria-label="Close"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>
              <p className="mb-2 text-[10px] uppercase tracking-[0.18em] text-white/40">Workspace</p>
              <div className="grid grid-cols-2 gap-2">
                {navItems
                  .filter((n) => !MOBILE_SHORTCUTS.includes(n.id))
                  .map((item) => {
                    const Icon = item.icon;
                    return (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => go(item.id)}
                        className="flex min-h-[48px] items-center gap-2 rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-left text-sm text-white"
                      >
                        <Icon className="h-4 w-4 shrink-0 text-exiqo-glow" />
                        <span className="truncate">{item.label}</span>
                      </button>
                    );
                  })}
              </div>
              <button
                type="button"
                onClick={() => {
                  setMobileMenuOpen(false);
                  onLogout();
                }}
                className="mt-4 flex w-full min-h-[48px] items-center justify-center gap-2 rounded-xl border border-rose-500/30 bg-rose-500/10 py-3 text-sm font-semibold text-rose-200"
              >
                <LogOut className="h-4 w-4" />
                Logout
              </button>
            </motion.div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </>
  );
};

export default Sidebar;
