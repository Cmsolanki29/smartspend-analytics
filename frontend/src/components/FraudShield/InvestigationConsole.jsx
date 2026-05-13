import React, { useState, useCallback, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Sparkles, Terminal } from "lucide-react";

const STEPS = [
  { text: "🔍 Analysing transaction context and merchant graph…", delay: 380 },
  { text: "✓ Checking merchant velocity… 47 txns in last hour (flag)", delay: 720 },
  { text: "✓ Cross-referencing fraud-ring database… no strong match", delay: 680 },
  { text: "✓ Comparing with your spending pattern… 23× avg ticket (flag)", delay: 760 },
  { text: "✓ Running SHAP explainability… top: unusual merchant + high amount", delay: 820 },
  { text: "📋 RECOMMENDATION: FLAG for manual review (confidence high)", delay: 520 },
];

export default function InvestigationConsole({ transactionLabel = "TXN-9981" }) {
  const [running, setRunning] = useState(false);
  const [lines, setLines] = useState([]);
  const timeoutsRef = useRef([]);

  const clearTimers = () => {
    timeoutsRef.current.forEach((id) => clearTimeout(id));
    timeoutsRef.current = [];
  };

  useEffect(() => () => clearTimers(), []);

  const run = useCallback(() => {
    clearTimers();
    setRunning(true);
    setLines([]);
    let t = 0;
    STEPS.forEach((step, i) => {
      t += step.delay;
      const id = window.setTimeout(() => {
        setLines((prev) => [...prev, step.text]);
        if (i === STEPS.length - 1) setRunning(false);
      }, t);
      timeoutsRef.current.push(id);
    });
  }, []);

  return (
    <div className="mb-6 rounded-2xl border border-violet-500/25 bg-gradient-to-br from-violet-500/10 to-slate-900/40 p-5 shadow-[0_0_40px_-12px_rgba(124,58,237,0.45)]">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 gap-3">
          <div className="mt-0.5 grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-white/10 bg-white/[0.06]">
            <Terminal className="h-5 w-5 text-violet-200" aria-hidden />
          </div>
          <div className="min-w-0">
            <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-violet-300/80">Phase 9 · Live console</p>
            <h3 className="mt-1 text-lg font-bold tracking-tight text-white">Investigation stream</h3>
            <p className="mt-1 max-w-xl text-xs leading-relaxed text-exiqo-glow/70">
              Our AI investigator analyses high-risk transactions like a fraud analyst — merchant velocity, ring signals,
              your spend curve, and SHAP drivers. Stream below is scripted; wire to{" "}
              <code className="rounded bg-black/30 px-1 text-[10px]">POST /risk/investigations/…/run</code> for live output.
            </p>
          </div>
        </div>
        <button
          type="button"
          disabled={running}
          onClick={run}
          className="inline-flex shrink-0 items-center gap-2 rounded-xl bg-gradient-to-r from-violet-600 to-blue-600 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-violet-500/30 transition hover:brightness-110 disabled:opacity-50"
        >
          <Sparkles className="h-4 w-4" aria-hidden />
          {running ? "Running…" : "Run investigation"}
        </button>
      </div>
      <div className="rounded-xl border border-white/10 bg-black/35 p-4 font-mono text-[11px] leading-relaxed text-emerald-100/90">
        <p className="mb-2 text-violet-200/80">Target: {transactionLabel}</p>
        {lines.length === 0 && !running ? (
          <p className="text-exiqo-glow/45">Press Run investigation to stream the agent trace.</p>
        ) : (
          <ul className="space-y-1.5">
            <AnimatePresence initial={false}>
              {lines.map((line, idx) => (
                <motion.li
                  key={`${idx}-${line.slice(0, 24)}`}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.2 }}
                  className="text-emerald-100/95"
                >
                  {line}
                </motion.li>
              ))}
            </AnimatePresence>
          </ul>
        )}
        {running ? <p className="mt-3 animate-pulse text-amber-200/85">Streaming agent…</p> : null}
      </div>
    </div>
  );
}
