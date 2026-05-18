import React, { useId, useMemo } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { FileWarning, Flag, IndianRupee, Users } from "lucide-react";
import type { MetricData } from "./mockData";
import { CHAINVAULT } from "./chainVaultTheme";

const ICONS = {
  flag: Flag,
  users: Users,
  rupee: IndianRupee,
  file: FileWarning,
} as const;

const ICON_TINT = {
  rose: { bg: "rgba(244, 63, 94, 0.12)", border: "rgba(244, 63, 94, 0.25)", icon: "#fb7185" },
  amber: { bg: "rgba(245, 158, 11, 0.12)", border: "rgba(245, 158, 11, 0.25)", icon: "#fbbf24" },
  muted: { bg: "rgba(139, 143, 168, 0.12)", border: "rgba(139, 143, 168, 0.25)", icon: "#8b8fa8" },
} as const;

function Sparkline({ values, color }: { values: number[]; color: string }) {
  const id = useId().replace(/:/g, "");
  const { points, area } = useMemo(() => {
    if (!values || values.length < 2) return { points: "", area: "" };
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = max - min || 1;
    const pts = values.map((v, i) => {
      const x = (i / (values.length - 1)) * 100;
      const y = 96 - ((v - min) / span) * 92;
      return [x, y] as const;
    });
    const polyline = pts.map(([x, y]) => `${x},${y}`).join(" ");
    const path = pts.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x},${y}`).join(" ");
    return { points: polyline, area: `${path} L100,100 L0,100 Z` };
  }, [values]);

  if (!points) return <div className="h-9" aria-hidden />;

  return (
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="h-9 w-full overflow-visible" aria-hidden>
      <defs>
        <linearGradient id={`fs-spark-${id}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.28" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#fs-spark-${id})`} />
      <polyline
        fill="none"
        stroke={color}
        strokeWidth={1.6}
        strokeLinecap="round"
        strokeLinejoin="round"
        points={points}
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

type Props = {
  metrics: MetricData[];
  premium?: boolean;
};

export default function MetricCards({ metrics, premium }: Props) {
  const reduce = useReducedMotion();

  return (
    <motion.div
      className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"
      initial={reduce ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: 0.08, ease: [0.22, 1, 0.36, 1] }}
    >
      {metrics.map((m, idx) => {
        const Icon = ICONS[m.icon];
        const tone = m.trendTone || "muted";
        const tint = ICON_TINT[tone === "rose" || tone === "amber" ? tone : "muted"];

        return (
          <motion.div
            key={m.id}
            initial={reduce ? false : { opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: reduce ? 0 : 0.06 * idx, duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
            className="relative overflow-hidden rounded-xl border p-6"
            style={{
              background: premium ? CHAINVAULT.cardBgElevated : "#1a1d27",
              borderColor: premium ? CHAINVAULT.goldBorderSoft : "rgba(255,255,255,0.06)",
              boxShadow: premium ? `0 0 40px -16px ${CHAINVAULT.goldGlow}` : undefined,
            }}
          >
            <div
              className="pointer-events-none absolute inset-0 opacity-[0.14]"
              style={{
                background: `radial-gradient(ellipse at bottom right, ${tint.icon} 0%, transparent 65%)`,
              }}
              aria-hidden
            />
            <div className="relative flex items-start justify-between gap-3">
              <div
                className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border"
                style={{ background: tint.bg, borderColor: tint.border }}
              >
                <Icon size={20} style={{ color: tint.icon }} aria-hidden />
              </div>
              {m.trend ? (
                <span
                  className="inline-flex rounded-full border px-2 py-0.5 text-[11px] font-semibold tabular-nums"
                  style={{
                    background: tint.bg,
                    borderColor: tint.border,
                    color: tint.icon,
                  }}
                >
                  {m.trend}
                </span>
              ) : null}
            </div>
            <p
              className="relative mt-5 text-[11px] font-semibold uppercase tracking-[0.12em]"
              style={{ color: premium ? CHAINVAULT.muted : "#8b8fa8" }}
            >
              {m.label}
            </p>
            <p className="relative mt-1.5 text-4xl font-bold tracking-tight text-white tabular-nums">{m.value}</p>
            {m.subtitle ? (
              <p className="relative mt-1 text-xs" style={{ color: premium ? CHAINVAULT.muted : "#8b8fa8" }}>
                {m.subtitle}
              </p>
            ) : null}
            <div className="relative mt-4 -mx-1">
              <Sparkline values={m.sparkline} color={m.sparkColor} />
            </div>
          </motion.div>
        );
      })}
    </motion.div>
  );
}
