import React, { useCallback, useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Pause, Play, Radio } from "lucide-react";
import { inr } from "../../lib/format";

const MERCHANTS = [
  "Swiggy", "Zomato", "Amazon Pay UPI", "PhonePe", "Blinkit", "Uber India", "BookMyShow", "Nykaa",
];

function mockEvent(i) {
  const statuses = ["REVIEW", "APPROVED", "BLOCKED"];
  const st = statuses[i % 3];
  const score = st === "BLOCKED" ? 88 + (i % 12) : st === "REVIEW" ? 52 + (i % 20) : 18 + (i % 15);
  return {
    id: `evt-${Date.now()}-${i}`,
    ts: new Date(),
    merchant: MERCHANTS[i % MERCHANTS.length],
    amount: [99, 149, 249, 499, 1299, 4500, 12000][i % 7],
    status: st,
    score,
  };
}

export default function FraudShieldLiveEventsTab({ userId }) {
  const [paused, setPaused] = useState(false);
  const [events, setEvents] = useState(() => Array.from({ length: 6 }, (_, i) => mockEvent(i)));

  const pushEvent = useCallback(() => {
    setEvents((prev) => [mockEvent(prev.length), ...prev].slice(0, 24));
  }, []);

  useEffect(() => {
    if (paused) return undefined;
    const id = window.setInterval(pushEvent, 5200);
    return () => clearInterval(id);
  }, [paused, pushEvent]);

  const epm = useMemo(() => {
    if (events.length < 2) return 0;
    return Math.min(12, Math.round(events.length / 2));
  }, [events.length]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-white/10 bg-white/[0.03] p-4 backdrop-blur-xl">
        <div className="flex items-center gap-3">
          <span className="relative flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-500/20 text-emerald-300">
            <Radio className="h-5 w-5" aria-hidden />
            <span className="absolute -right-0.5 -top-0.5 h-2 w-2 animate-pulse rounded-full bg-emerald-400 shadow-[0_0_8px_#34d399]" />
          </span>
          <div>
            <p className="text-sm font-semibold text-white">Live protection stream</p>
            <p className="text-xs text-exiqo-glow/60">
              Simulated feed for user <span className="tabular-nums text-white/80">{userId}</span> — wire to WebSocket when ready.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-center">
            <p className="text-[10px] uppercase tracking-wider text-exiqo-glow/50">Events / min</p>
            <p className="text-lg font-bold tabular-nums text-white">{epm}</p>
          </div>
          <button
            type="button"
            onClick={() => setPaused((p) => !p)}
            className="inline-flex items-center gap-2 rounded-xl border border-white/15 bg-white/[0.06] px-4 py-2 text-sm font-medium text-white transition hover:bg-white/10"
          >
            {paused ? <Play className="h-4 w-4" /> : <Pause className="h-4 w-4" />}
            {paused ? "Resume" : "Pause stream"}
          </button>
        </div>
      </div>

      <ul className="space-y-2">
        <AnimatePresence initial={false}>
          {events.map((e) => (
            <motion.li
              key={e.id}
              layout
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ type: "spring", stiffness: 420, damping: 32 }}
              className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-white/[0.07] bg-white/[0.025] px-4 py-3 backdrop-blur-md"
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-white">{e.merchant}</p>
                <p className="text-[11px] tabular-nums text-exiqo-glow/55">
                  {e.ts.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                </p>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-sm font-semibold tabular-nums text-white">{inr(e.amount)}</span>
                <span
                  className={`rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${
                    e.status === "BLOCKED"
                      ? "bg-rose-500/25 text-rose-200 ring-1 ring-rose-500/40"
                      : e.status === "REVIEW"
                        ? "bg-amber-500/20 text-amber-100 ring-1 ring-amber-500/35"
                        : "bg-emerald-500/20 text-emerald-100 ring-1 ring-emerald-500/30"
                  }`}
                >
                  {e.status}
                </span>
                <span className="text-xs tabular-nums text-exiqo-glow/50">score {e.score}</span>
              </div>
            </motion.li>
          ))}
        </AnimatePresence>
      </ul>
    </div>
  );
}
