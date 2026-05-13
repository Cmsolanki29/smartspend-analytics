import React from "react";
import { motion } from "framer-motion";

export function PhaseCard({ phase, Icon, index }) {
  const Ico = Icon;
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.045, type: "spring", stiffness: 380, damping: 28 }}
      whileHover={{ y: -5, transition: { duration: 0.15 } }}
      className="group snap-start rounded-2xl border border-white/[0.08] bg-white/[0.04] p-4 shadow-[0_12px_40px_-28px_rgba(0,0,0,0.85)] transition-[box-shadow,border-color] duration-300 hover:border-violet-400/40 hover:shadow-[0_0_36px_-12px_rgba(124,58,237,0.5)]"
    >
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-violet-500/20 text-xs font-bold tabular-nums text-violet-200 ring-1 ring-violet-400/30">
          {phase.n}
        </span>
        <span className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400/50" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
        </span>
      </div>
      <div className="mb-2 flex items-center gap-2 text-violet-200/90">
        <Ico className="h-4 w-4 shrink-0" aria-hidden />
        <span className="text-sm font-semibold leading-tight tracking-tight text-white">{phase.name}</span>
      </div>
      <p className="text-[11px] leading-snug text-exiqo-glow/65">{phase.blurb}</p>
      <p className="mt-2 max-h-0 overflow-hidden text-[10px] leading-snug text-exiqo-glow/55 transition-all duration-300 group-hover:max-h-20">
        {phase.hoverDetail || `Phase ${phase.n} — ${phase.name} — live on your transaction graph.`}
      </p>
    </motion.div>
  );
}
