import React from "react";
import { motion, useReducedMotion } from "framer-motion";
import { ChevronRight } from "lucide-react";
import type { AlertCardData } from "./mockData";
import { CHAINVAULT } from "./chainVaultTheme";

const VARIANT_STYLES = {
  critical: {
    border: "1px solid rgba(239, 68, 68, 0.35)",
    shadow: "0 0 20px rgba(239, 68, 68, 0.08)",
    badgeBg: "rgba(239, 68, 68, 0.18)",
    badgeColor: "rgb(252, 165, 165)",
  },
  warning: {
    border: "1px solid rgba(234, 179, 8, 0.35)",
    shadow: "0 0 20px rgba(234, 179, 8, 0.08)",
    badgeBg: "rgba(234, 179, 8, 0.18)",
    badgeColor: "rgb(253, 224, 71)",
  },
  monitoring: {
    border: "1px solid rgba(124, 58, 237, 0.35)",
    shadow: "0 0 20px rgba(124, 58, 237, 0.1)",
    badgeBg: "rgba(124, 58, 237, 0.2)",
    badgeColor: "rgb(196, 181, 253)",
  },
} as const;

type Props = {
  cards: AlertCardData[];
  onCta?: (id: string) => void;
  premium?: boolean;
};

export default function AlertCards({ cards, onCta, premium }: Props) {
  const reduce = useReducedMotion();

  return (
    <motion.div
      className="grid gap-4 md:grid-cols-2 lg:grid-cols-3"
      initial={reduce ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
    >
      {cards.map((c, idx) => {
        const vs = VARIANT_STYLES[c.variant];
        return (
          <motion.button
            key={c.id}
            type="button"
            onClick={() => onCta?.(c.id)}
            initial={reduce ? false : { opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: reduce ? 0 : 0.05 * idx, duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
            className="group w-full rounded-xl p-5 text-left transition-opacity duration-200 hover:opacity-95"
            style={{
              background: premium ? CHAINVAULT.cardBgElevated : "#1a1d27",
              border: vs.border,
              boxShadow: premium ? `${vs.shadow}, 0 0 32px -16px ${CHAINVAULT.goldGlow}` : vs.shadow,
            }}
          >
            <span
              className="inline-block rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide"
              style={{ background: vs.badgeBg, color: vs.badgeColor }}
            >
              {c.badge}
            </span>
            <h3 className="mt-3 text-base font-semibold leading-snug text-white">{c.title}</h3>
            <p className="mt-2 text-sm leading-relaxed" style={{ color: premium ? CHAINVAULT.muted : "#8b8fa8" }}>
              {c.body}
            </p>
            <div className="mt-4 flex items-end justify-between gap-3">
              <div>
                <p
                  className="text-[11px] font-semibold uppercase tracking-wide"
                  style={{ color: premium ? CHAINVAULT.muted : "#8b8fa8" }}
                >
                  {c.metricLabel}
                </p>
                <p className="mt-0.5 text-xl font-semibold tabular-nums text-white">{c.metricValue}</p>
              </div>
              <span
                className={[
                  "inline-flex items-center gap-1 rounded-lg border px-3 py-2 text-xs font-semibold transition",
                  premium ? "group-hover:opacity-90" : "border-white/15 bg-white/[0.06] text-white group-hover:bg-white/[0.1]",
                ].join(" ")}
                style={
                  premium
                    ? {
                        borderColor: CHAINVAULT.goldBorderSoft,
                        background: "rgba(212,175,55,0.1)",
                        color: CHAINVAULT.goldLight,
                      }
                    : undefined
                }
              >
                {c.ctaLabel}
                <ChevronRight className="h-3.5 w-3.5 transition group-hover:translate-x-0.5" strokeWidth={1.75} aria-hidden />
              </span>
            </div>
          </motion.button>
        );
      })}
    </motion.div>
  );
}
