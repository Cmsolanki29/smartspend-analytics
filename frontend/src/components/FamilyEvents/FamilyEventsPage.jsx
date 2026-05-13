/**
 * FamilyEventsPage — Trips & Events manager.
 * Create, postpone, complete family events. Cascade to linked purchase goals.
 * Every change recalculates the financial engine automatically.
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  AlertTriangle,
  CalendarDays,
  CheckCircle2,
  ChevronRight,
  Clock,
  Plus,
  RefreshCw,
  Trash2,
  X,
} from "lucide-react";
import {
  completeFamilyEvent,
  deleteFamilyEvent,
  getFamilyEvents,
  getPurchases,
  postponeFamilyEvent,
  postFamilyEvent,
} from "../../services/api";
import { GlassCard } from "../intro/GlassCard";
import { inr } from "../../lib/format";

const STATUS_LABELS = {
  planned:   { label: "Planned",   cls: "border-sky-500/30 bg-sky-500/10 text-sky-300" },
  postponed: { label: "Postponed", cls: "border-amber-500/30 bg-amber-500/10 text-amber-300" },
  completed: { label: "Completed", cls: "border-emerald-500/30 bg-emerald-500/10 text-emerald-300" },
  cancelled: { label: "Cancelled", cls: "border-white/10 bg-white/[0.04] text-white/40" },
};

function StatusBadge({ status }) {
  const cfg = STATUS_LABELS[status] || STATUS_LABELS.planned;
  return <span className={`rounded-full border px-2.5 py-0.5 text-[11px] font-medium ${cfg.cls}`}>{cfg.label}</span>;
}

function EventCard({ event, goals, onPostpone, onComplete, onDelete }) {
  const [showPostpone, setShowPostpone] = useState(false);
  const [newDate, setNewDate] = useState("");
  const [reason, setReason] = useState("");
  const [cascadeGoal, setCascadeGoal] = useState(true);
  const [loading, setLoading] = useState(false);

  const effectiveDate = event.postponed_to_date || event.planned_date;
  const daysLeft = effectiveDate
    ? Math.ceil((new Date(effectiveDate) - new Date()) / 86_400_000)
    : null;

  const linkedGoal = goals.find((g) => g.goal_id === event.linked_purchase_goal_id);

  const handlePostpone = async () => {
    if (!newDate) return;
    setLoading(true);
    try {
      await onPostpone(event.id, { new_date: newDate, reason, cascade_linked_goal: cascadeGoal });
      setShowPostpone(false);
      setNewDate("");
      setReason("");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="rounded-2xl border border-white/[0.08] bg-white/[0.02] backdrop-blur-xl">
      <div className="flex flex-col gap-3 p-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <span className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-exiqo-purple/30 bg-exiqo-purple/15">
            <CalendarDays className="h-5 w-5 text-exiqo-purple" aria-hidden />
          </span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="font-heading text-base font-semibold text-white">{event.event_name}</h3>
              <StatusBadge status={event.status} />
            </div>
            <div className="mt-1 flex flex-wrap gap-3 text-xs text-exiqo-glow/60">
              <span>
                {event.status === "postponed" ? "Moved to" : "Planned"}:{" "}
                <span className={`font-medium ${event.status === "postponed" ? "text-amber-300" : "text-white/80"}`}>
                  {effectiveDate
                    ? new Date(effectiveDate).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })
                    : "—"}
                </span>
              </span>
              {daysLeft !== null && event.status !== "completed" && event.status !== "cancelled" && (
                <span className={daysLeft < 0 ? "text-rose-300" : daysLeft < 30 ? "text-amber-300" : "text-exiqo-glow/60"}>
                  {daysLeft < 0 ? `${Math.abs(daysLeft)}d overdue` : `${daysLeft}d away`}
                </span>
              )}
            </div>
            {linkedGoal && (
              <p className="mt-1.5 text-[11px] text-sky-300/80">
                Linked: {linkedGoal.item_name} purchase plan
                {event.status === "postponed" ? " (auto-updated to match)" : ""}
              </p>
            )}
            {event.postpone_reason && (
              <p className="mt-1 text-[11px] text-amber-100/60">Reason: {event.postpone_reason}</p>
            )}
            {event.notes && <p className="mt-1 text-[11px] text-exiqo-glow/50">{event.notes}</p>}
          </div>
        </div>

        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <p className="font-heading text-lg font-bold text-white">{inr(event.estimated_cost)}</p>
          {event.status !== "completed" && event.status !== "cancelled" && (
            <>
              <button
                type="button"
                onClick={() => setShowPostpone((s) => !s)}
                className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-xs font-semibold text-amber-200 transition hover:bg-amber-500/20"
              >
                {showPostpone ? "Cancel" : "Postpone"}
              </button>
              <button
                type="button"
                onClick={() => onComplete(event.id)}
                className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-3 py-1.5 text-xs font-semibold text-emerald-200 transition hover:bg-emerald-500/20"
              >
                <CheckCircle2 className="inline h-3.5 w-3.5 mr-1" aria-hidden />Done
              </button>
            </>
          )}
          <button
            type="button"
            onClick={() => onDelete(event.id)}
            className="rounded-xl border border-white/10 p-1.5 text-exiqo-glow/40 transition hover:border-rose-500/30 hover:text-rose-300"
          >
            <Trash2 className="h-4 w-4" aria-hidden />
          </button>
        </div>
      </div>

      {/* Postpone form */}
      <AnimatePresence>
        {showPostpone && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden border-t border-white/[0.06]"
          >
            <div className="space-y-3 p-4">
              <p className="text-xs font-semibold text-white/70">Move event to new date</p>
              <div className="grid gap-3 sm:grid-cols-2">
                <div>
                  <label className="mb-1 block text-[11px] text-exiqo-glow/60">New date *</label>
                  <input
                    type="date"
                    value={newDate}
                    onChange={(e) => setNewDate(e.target.value)}
                    min={new Date().toISOString().split("T")[0]}
                    className="w-full rounded-xl border border-white/10 bg-[#070418]/80 px-3 py-2 text-sm text-white focus:border-exiqo-purple/50 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-[11px] text-exiqo-glow/60">Reason (optional)</label>
                  <input
                    type="text"
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    placeholder="e.g. Budget constraint"
                    className="w-full rounded-xl border border-white/10 bg-[#070418]/80 px-3 py-2 text-sm text-white placeholder:text-exiqo-glow/30 focus:border-exiqo-purple/50 focus:outline-none"
                  />
                </div>
              </div>
              {linkedGoal && (
                <label className="flex cursor-pointer items-center gap-2 text-xs text-exiqo-glow/80">
                  <input
                    type="checkbox"
                    checked={cascadeGoal}
                    onChange={(e) => setCascadeGoal(e.target.checked)}
                    className="rounded border-white/20 bg-transparent accent-exiqo-purple"
                  />
                  Also update "{linkedGoal.item_name}" purchase plan target date to match
                  <span className="ml-1 rounded-full bg-sky-500/15 px-2 py-0.5 text-[10px] text-sky-300">Recommended</span>
                </label>
              )}
              <div className="flex gap-2">
                <button
                  type="button"
                  disabled={!newDate || loading}
                  onClick={handlePostpone}
                  className="flex-1 rounded-xl bg-gradient-to-r from-exiqo-purple to-exiqo-pink py-2 text-xs font-semibold text-white disabled:opacity-40"
                >
                  {loading ? "Moving…" : "Confirm postpone"}
                </button>
                <button
                  type="button"
                  onClick={() => setShowPostpone(false)}
                  className="rounded-xl border border-white/10 px-3 py-2 text-xs text-exiqo-glow/70"
                >
                  <X className="h-4 w-4" aria-hidden />
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function AddEventModal({ userId, goals, onAdded, onClose }) {
  const [form, setForm] = useState({
    event_name: "",
    event_type: "trip",
    planned_date: "",
    estimated_cost: "",
    linked_purchase_goal_id: "",
    notes: "",
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.event_name || !form.planned_date || !form.estimated_cost) {
      setError("Name, date and cost are required.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      await postFamilyEvent(userId, {
        ...form,
        estimated_cost: Number(form.estimated_cost),
        linked_purchase_goal_id: form.linked_purchase_goal_id ? Number(form.linked_purchase_goal_id) : null,
      });
      onAdded();
    } catch (err) {
      setError(err?.response?.data?.detail || err?.message || "Could not create event");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 backdrop-blur-sm">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className="relative z-10 w-full max-w-lg rounded-2xl border border-white/[0.10] bg-[#0c0c1e] p-6 shadow-2xl"
      >
        <div className="mb-5 flex items-center justify-between">
          <h2 className="font-heading text-lg font-bold text-white">Add Trip / Event</h2>
          <button type="button" onClick={onClose} className="rounded-full p-1 text-exiqo-glow/50 hover:text-white">
            <X className="h-5 w-5" aria-hidden />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="mb-1 block text-xs text-exiqo-glow/60">Event name *</label>
            <input
              type="text"
              value={form.event_name}
              onChange={(e) => setForm((f) => ({ ...f, event_name: e.target.value }))}
              placeholder="Family trip to Goa"
              className="w-full rounded-xl border border-white/10 bg-[#070418]/80 px-3 py-2.5 text-sm text-white placeholder:text-exiqo-glow/30 focus:border-exiqo-purple/50 focus:outline-none"
            />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-xs text-exiqo-glow/60">Type</label>
              <select
                value={form.event_type}
                onChange={(e) => setForm((f) => ({ ...f, event_type: e.target.value }))}
                className="w-full rounded-xl border border-white/10 bg-[#070418]/80 px-3 py-2.5 text-sm text-white focus:border-exiqo-purple/50 focus:outline-none"
              >
                <option value="trip">Trip</option>
                <option value="celebration">Celebration</option>
                <option value="medical">Medical</option>
                <option value="other">Other</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs text-exiqo-glow/60">Planned date *</label>
              <input
                type="date"
                value={form.planned_date}
                onChange={(e) => setForm((f) => ({ ...f, planned_date: e.target.value }))}
                min={new Date().toISOString().split("T")[0]}
                className="w-full rounded-xl border border-white/10 bg-[#070418]/80 px-3 py-2.5 text-sm text-white focus:border-exiqo-purple/50 focus:outline-none"
              />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-xs text-exiqo-glow/60">Estimated cost (₹) *</label>
            <input
              type="number"
              value={form.estimated_cost}
              onChange={(e) => setForm((f) => ({ ...f, estimated_cost: e.target.value }))}
              placeholder="45000"
              min="0"
              className="w-full rounded-xl border border-white/10 bg-[#070418]/80 px-3 py-2.5 text-sm text-white placeholder:text-exiqo-glow/30 focus:border-exiqo-purple/50 focus:outline-none"
            />
          </div>
          {goals.length > 0 && (
            <div>
              <label className="mb-1 block text-xs text-exiqo-glow/60">
                Link to purchase goal (optional — will cascade when postponed)
              </label>
              <select
                value={form.linked_purchase_goal_id}
                onChange={(e) => setForm((f) => ({ ...f, linked_purchase_goal_id: e.target.value }))}
                className="w-full rounded-xl border border-white/10 bg-[#070418]/80 px-3 py-2.5 text-sm text-white focus:border-exiqo-purple/50 focus:outline-none"
              >
                <option value="">— None —</option>
                {goals.map((g) => (
                  <option key={g.goal_id} value={g.goal_id}>{g.item_name}</option>
                ))}
              </select>
            </div>
          )}
          <div>
            <label className="mb-1 block text-xs text-exiqo-glow/60">Notes (optional)</label>
            <input
              type="text"
              value={form.notes}
              onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
              placeholder="Booking details, reminders…"
              className="w-full rounded-xl border border-white/10 bg-[#070418]/80 px-3 py-2.5 text-sm text-white placeholder:text-exiqo-glow/30 focus:border-exiqo-purple/50 focus:outline-none"
            />
          </div>
          {error && <p className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">{error}</p>}
          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-xl bg-gradient-to-r from-exiqo-purple to-exiqo-pink py-3 text-sm font-semibold text-white shadow-ss-cta transition hover:shadow-ss-cta-hover disabled:opacity-50"
          >
            {loading ? "Adding…" : "Add event"}
          </button>
        </form>
      </motion.div>
    </div>
  );
}

export default function FamilyEventsPage({ userId }) {
  const [state, setState] = useState({ loading: true, error: "", events: [] });
  const [goals, setGoals] = useState([]);
  const [showAdd, setShowAdd] = useState(false);
  const [toast, setToast] = useState("");

  const load = useCallback(async () => {
    setState((s) => ({ ...s, loading: true, error: "" }));
    try {
      const [evts, goalsRes] = await Promise.all([
        getFamilyEvents(userId),
        getPurchases(userId).catch(() => ({ goals: [] })),
      ]);
      setState({ loading: false, error: "", events: Array.isArray(evts) ? evts : [] });
      setGoals(goalsRes?.goals || []);
    } catch (err) {
      setState({ loading: false, error: err?.message || "Could not load events", events: [] });
    }
  }, [userId]);

  useEffect(() => { load(); }, [load]);

  const showToast = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(""), 4000);
  };

  const handlePostpone = async (eventId, body) => {
    try {
      const res = await postponeFamilyEvent(userId, eventId, body);
      showToast(res?.notification || "Event moved. Financial state recalculated.");
      // Dispatch events so Dashboard and EMI tracker reload
      window.dispatchEvent(new CustomEvent("smartspend-financial-sync", { detail: { userId } }));
      await load();
    } catch (err) {
      showToast("Error: " + (err?.response?.data?.detail || err?.message || "Could not postpone"));
    }
  };

  const handleComplete = async (eventId) => {
    try {
      await completeFamilyEvent(userId, eventId);
      showToast("Event marked as completed!");
      window.dispatchEvent(new CustomEvent("smartspend-financial-sync", { detail: { userId } }));
      await load();
    } catch (err) {
      showToast("Error: " + (err?.message || "Could not complete"));
    }
  };

  const handleDelete = async (eventId) => {
    if (!window.confirm("Cancel this event?")) return;
    try {
      await deleteFamilyEvent(userId, eventId);
      window.dispatchEvent(new CustomEvent("smartspend-financial-sync", { detail: { userId } }));
      await load();
    } catch (err) {
      showToast("Error: " + (err?.message || "Could not cancel"));
    }
  };

  const active = useMemo(() => state.events.filter((e) => e.status !== "cancelled"), [state.events]);
  const upcoming = useMemo(() => active.filter((e) => e.status !== "completed"), [active]);
  const done = useMemo(() => active.filter((e) => e.status === "completed"), [active]);

  if (state.loading) {
    return (
      <div className="space-y-4">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-24 animate-pulse rounded-2xl border border-white/[0.06] bg-white/[0.02]" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-6 pb-8">
      {/* Toast */}
      <AnimatePresence>
        {toast && (
          <motion.div
            key="toast"
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="fixed left-1/2 top-6 z-50 -translate-x-1/2 rounded-2xl border border-emerald-500/40 bg-emerald-500/20 px-5 py-3 text-sm font-medium text-emerald-100 shadow-xl backdrop-blur-xl"
          >
            {toast}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-widest text-exiqo-glow/50">Family Finance</p>
          <h1 className="font-heading text-2xl font-bold text-white">Trips &amp; Events</h1>
          <p className="mt-1 text-sm text-exiqo-glow/60">
            Postponing a trip auto-updates linked purchase plans. Every change recalculates your budget.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={load}
            className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-xs font-medium text-exiqo-glow/70 transition hover:bg-white/[0.08]"
          >
            <RefreshCw className="h-3.5 w-3.5" aria-hidden />Refresh
          </button>
          <button
            type="button"
            onClick={() => setShowAdd(true)}
            className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-exiqo-purple to-exiqo-pink px-4 py-2 text-xs font-semibold text-white shadow-ss-cta transition hover:shadow-ss-cta-hover"
          >
            <Plus className="h-4 w-4" aria-hidden />Add event
          </button>
        </div>
      </div>

      {state.error && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
          {state.error}
        </div>
      )}

      {/* Cascade note */}
      <div className="rounded-2xl border border-sky-500/25 bg-sky-500/8 px-4 py-3">
        <div className="flex items-start gap-2 text-xs text-sky-200/80">
          <ChevronRight className="mt-0.5 h-3.5 w-3.5 shrink-0 text-sky-400" aria-hidden />
          <p>
            <strong className="text-sky-200">Cascade rule:</strong> When you postpone a trip, any linked purchase plan
            target date is automatically moved to match, and monthly saving pace is recalculated. Your dashboard
            surplus updates instantly.
          </p>
        </div>
      </div>

      {/* Upcoming */}
      {upcoming.length === 0 && done.length === 0 ? (
        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] py-16 text-center">
          <CalendarDays className="mx-auto mb-3 h-12 w-12 text-exiqo-glow/30" aria-hidden />
          <p className="font-heading text-lg font-semibold text-white">No events planned</p>
          <p className="mx-auto mt-2 max-w-sm text-sm text-exiqo-glow/50">
            Add a family trip or event and link it to a purchase goal — postponing one will auto-update the other.
          </p>
          <button
            type="button"
            onClick={() => setShowAdd(true)}
            className="mt-4 inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-exiqo-purple to-exiqo-pink px-5 py-2.5 text-sm font-semibold text-white"
          >
            <Plus className="h-4 w-4" aria-hidden />Add your first event
          </button>
        </div>
      ) : (
        <>
          {upcoming.length > 0 && (
            <div className="space-y-3">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-exiqo-glow/70">
                <Clock className="h-4 w-4" aria-hidden />Upcoming ({upcoming.length})
              </h2>
              {upcoming.map((e) => (
                <EventCard
                  key={e.id}
                  event={e}
                  goals={goals}
                  onPostpone={handlePostpone}
                  onComplete={handleComplete}
                  onDelete={handleDelete}
                />
              ))}
            </div>
          )}

          {done.length > 0 && (
            <div className="space-y-3">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-exiqo-glow/50">
                <CheckCircle2 className="h-4 w-4" aria-hidden />Completed ({done.length})
              </h2>
              {done.map((e) => (
                <EventCard
                  key={e.id}
                  event={e}
                  goals={goals}
                  onPostpone={handlePostpone}
                  onComplete={handleComplete}
                  onDelete={handleDelete}
                />
              ))}
            </div>
          )}
        </>
      )}

      {/* Add Event Modal */}
      {showAdd && (
        <AddEventModal
          userId={userId}
          goals={goals}
          onAdded={async () => {
            setShowAdd(false);
            window.dispatchEvent(new CustomEvent("smartspend-financial-sync", { detail: { userId } }));
            await load();
          }}
          onClose={() => setShowAdd(false)}
        />
      )}
    </div>
  );
}
