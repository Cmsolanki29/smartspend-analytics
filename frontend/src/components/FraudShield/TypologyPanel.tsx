import React, { useState } from "react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import type { TypologyData, TypologyId } from "./mockData";
import { CHAINVAULT } from "./chainVaultTheme";

const DOT: Record<string, string> = {
  rose: "#fb7185",
  amber: "#fbbf24",
  purple: "#a855f7",
  cyan: "#22d3ee",
};

function riskBarColor(score: number) {
  if (score >= 90) return "#ef4444";
  if (score >= 80) return "#f59e0b";
  return "#3b82f6";
}

type Props = {
  typologies: TypologyData[];
  premium?: boolean;
};

export default function TypologyPanel({ typologies, premium }: Props) {
  const reduce = useReducedMotion();
  const [active, setActive] = useState<TypologyId>(typologies[0]?.id ?? "mule-chain");
  const selected = typologies.find((t) => t.id === active) ?? typologies[0];

  return (
    <section className="mt-6">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-[0.14em] text-white">Fraud typologies</h2>
        <p className="text-xs" style={{ color: premium ? CHAINVAULT.muted : "#8b8fa8" }}>
          Tap a pattern to inspect indicators
        </p>
      </div>

      <div className="-mx-1 flex gap-3 overflow-x-auto px-1 pb-2">
        {typologies.map((t) => {
          const isActive = t.id === active;
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => setActive(t.id)}
              className="min-w-[148px] shrink-0 rounded-xl border p-4 text-left transition"
              style={{
                background: isActive
                  ? premium
                    ? "rgba(212, 175, 55, 0.1)"
                    : "rgba(124, 58, 237, 0.12)"
                  : premium
                    ? CHAINVAULT.cardBgElevated
                    : "#1a1d27",
                borderColor: isActive
                  ? premium
                    ? CHAINVAULT.goldBorder
                    : "rgba(124, 58, 237, 0.45)"
                  : premium
                    ? CHAINVAULT.goldBorderSoft
                    : "rgba(255,255,255,0.06)",
              }}
            >
              <p className="text-sm font-semibold text-white">{t.name}</p>
              <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
                <div
                  className="h-full rounded-full transition-all duration-300"
                  style={{ width: `${t.riskScore}%`, background: riskBarColor(t.riskScore) }}
                />
              </div>
              <p className="mt-2 text-xs tabular-nums" style={{ color: premium ? CHAINVAULT.muted : "#8b8fa8" }}>
                Risk {t.riskScore}/100
              </p>
            </button>
          );
        })}
      </div>

      <AnimatePresence mode="wait">
        {selected ? (
          <motion.div
            key={selected.id}
            initial={reduce ? false : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reduce ? undefined : { opacity: 0, y: -6 }}
            transition={{ duration: 0.25 }}
            className="mt-4 grid gap-4 rounded-xl border border-white/[0.06] p-6 lg:grid-cols-2"
            style={{
              background: premium ? CHAINVAULT.cardBgElevated : "#1a1d27",
              borderColor: premium ? CHAINVAULT.goldBorderSoft : undefined,
            }}
          >
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-[0.14em]" style={{ color: "#8b8fa8" }}>
                Behavioral indicators
              </h3>
              <ul className="mt-3 space-y-2.5">
                {selected.indicators.map((ind) => (
                  <li key={ind.text} className="flex items-start gap-2.5 text-sm text-gray-300">
                    <span
                      className="mt-1.5 h-2 w-2 shrink-0 rounded-full"
                      style={{ background: DOT[ind.tone] || DOT.purple }}
                      aria-hidden
                    />
                    {ind.text}
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-[0.14em]" style={{ color: "#8b8fa8" }}>
                Detection controls
              </h3>
              <div className="mt-3 flex flex-wrap gap-2">
                {selected.controls.map((tag) => (
                  <span
                    key={tag}
                    className="rounded-full border border-purple-500/30 bg-purple-500/10 px-2.5 py-1 text-xs font-medium text-purple-200"
                  >
                    {tag}
                  </span>
                ))}
              </div>
              <h3 className="mt-5 text-xs font-semibold uppercase tracking-[0.14em]" style={{ color: "#8b8fa8" }}>
                Evasion tactics
              </h3>
              <ul className="mt-3 space-y-2 text-sm text-gray-400">
                {selected.evasion.map((e) => (
                  <li key={e} className="flex items-center gap-2">
                    <span className="text-amber-400/80" aria-hidden>
                      ›
                    </span>
                    {e}
                  </li>
                ))}
              </ul>
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </section>
  );
}
