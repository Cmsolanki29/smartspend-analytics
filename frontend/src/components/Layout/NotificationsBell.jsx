/**
 * NotificationsBell — Bell icon with unread badge and dropdown panel.
 * Every cascade writes a notification; this surfaces them.
 */
import React, { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, Bell, BellRing, CheckCircle2, Info, X } from "lucide-react";
import { getNotifications, markNotificationsRead } from "../../services/api";

const TYPE_CONFIG = {
  alert:   { icon: AlertTriangle, color: "text-rose-300",   bg: "bg-rose-500/10 border-rose-500/25" },
  warning: { icon: AlertTriangle, color: "text-amber-300",  bg: "bg-amber-500/10 border-amber-500/25" },
  success: { icon: CheckCircle2,  color: "text-emerald-300",bg: "bg-emerald-500/10 border-emerald-500/25" },
  info:    { icon: Info,          color: "text-sky-300",    bg: "bg-sky-500/10 border-sky-500/25" },
};

function NotifItem({ n, onMarkRead }) {
  const cfg = TYPE_CONFIG[n.type] || TYPE_CONFIG.info;
  const Icon = cfg.icon;
  const ts = n.created_at
    ? new Date(n.created_at).toLocaleString("en-IN", { dateStyle: "short", timeStyle: "short" })
    : "";
  return (
    <div className={`flex gap-3 rounded-xl border p-3 ${cfg.bg} ${!n.is_read ? "ring-1 ring-inset ring-white/10" : "opacity-70"}`}>
      <span className="mt-0.5 shrink-0">
        <Icon className={`h-4 w-4 ${cfg.color}`} aria-hidden />
      </span>
      <div className="min-w-0 flex-1">
        <p className={`text-xs font-semibold text-white ${!n.is_read ? "" : "opacity-80"}`}>{n.title}</p>
        <p className="mt-0.5 text-[11px] leading-relaxed text-exiqo-glow/75">{n.body}</p>
        <p className="mt-1 text-[10px] text-exiqo-glow/40">{ts}</p>
      </div>
      {!n.is_read && (
        <button
          type="button"
          onClick={() => onMarkRead(n.id)}
          className="shrink-0 self-start rounded-full p-0.5 text-exiqo-glow/40 transition hover:text-white"
          title="Mark read"
        >
          <X className="h-3.5 w-3.5" aria-hidden />
        </button>
      )}
    </div>
  );
}

export default function NotificationsBell({ userId }) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState({ unread_count: 0, notifications: [] });
  const [loading, setLoading] = useState(false);
  const panelRef = useRef(null);

  const load = useCallback(async () => {
    if (!userId) return;
    setLoading(true);
    try {
      const res = await getNotifications(userId, { limit: 20, unreadOnly: false });
      setData(res || { unread_count: 0, notifications: [] });
    } catch {
      /* silent */
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => { load(); }, [load]);

  // Poll every 60 seconds
  useEffect(() => {
    const interval = setInterval(load, 60_000);
    return () => clearInterval(interval);
  }, [load]);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e) => {
      if (panelRef.current && !panelRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const handleMarkRead = async (notifId) => {
    try {
      await markNotificationsRead(userId, { notification_ids: [notifId] });
      setData((d) => ({
        ...d,
        unread_count: Math.max(0, d.unread_count - 1),
        notifications: d.notifications.map((n) => (n.id === notifId ? { ...n, is_read: true } : n)),
      }));
    } catch {/* silent */}
  };

  const handleMarkAll = async () => {
    try {
      await markNotificationsRead(userId, { mark_all: true });
      setData((d) => ({
        ...d,
        unread_count: 0,
        notifications: d.notifications.map((n) => ({ ...n, is_read: true })),
      }));
    } catch {/* silent */}
  };

  const unread = data.unread_count || 0;
  const notifs = data.notifications || [];

  return (
    <div className="relative" ref={panelRef}>
      <button
        type="button"
        onClick={() => { setOpen((o) => !o); if (!open) load(); }}
        className="relative flex h-9 w-9 items-center justify-center rounded-full border border-white/10 bg-white/[0.05] text-exiqo-glow/80 transition hover:bg-white/[0.10] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60"
        aria-label={`Notifications${unread > 0 ? ` (${unread} unread)` : ""}`}
      >
        {unread > 0 ? <BellRing className="h-4.5 w-4.5" aria-hidden /> : <Bell className="h-4.5 w-4.5" aria-hidden />}
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-rose-500 text-[10px] font-bold text-white">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            key="notif-panel"
            initial={{ opacity: 0, y: -8, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.96 }}
            transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
            className="absolute right-0 top-11 z-50 w-80 rounded-2xl border border-white/[0.10] bg-[#0c0c1e]/95 p-3 shadow-2xl backdrop-blur-xl sm:w-96"
          >
            {/* Panel header */}
            <div className="mb-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <BellRing className="h-4 w-4 text-exiqo-glow/60" aria-hidden />
                <span className="text-sm font-semibold text-white">Notifications</span>
                {unread > 0 && (
                  <span className="rounded-full bg-rose-500/20 px-2 py-0.5 text-[10px] font-bold text-rose-300">
                    {unread} new
                  </span>
                )}
              </div>
              {unread > 0 && (
                <button
                  type="button"
                  onClick={handleMarkAll}
                  className="text-[11px] text-exiqo-glow/55 underline transition hover:text-white"
                >
                  Mark all read
                </button>
              )}
            </div>

            {/* Notifications list */}
            <div className="max-h-[380px] space-y-2 overflow-y-auto">
              {loading && notifs.length === 0 && (
                <div className="space-y-2">
                  {[1, 2, 3].map((i) => <div key={i} className="h-16 animate-pulse rounded-xl bg-white/[0.04]" />)}
                </div>
              )}
              {!loading && notifs.length === 0 && (
                <div className="py-8 text-center text-sm text-exiqo-glow/50">
                  <Bell className="mx-auto mb-2 h-8 w-8 opacity-30" aria-hidden />
                  No notifications yet
                </div>
              )}
              {notifs.map((n) => (
                <NotifItem key={n.id} n={n} onMarkRead={handleMarkRead} />
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
