import { motion, useReducedMotion } from "framer-motion";
import type { LucideIcon } from "lucide-react";
import { TrendingDown, TrendingUp } from "lucide-react";
import { GlassCard } from "../../intro/GlassCard";

export type KPITileProps = {
  title: string;
  value: string;
  subtitle?: string;
  icon?: LucideIcon;
  trendPct?: number | null;
  sparklineValues?: number[];
  delay?: number;
  className?: string;
};

function Sparkline({ values }: { values: number[] }) {
  if (!values.length) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const pts = values.map((v, i) => {
    const x = (i / Math.max(1, values.length - 1)) * 100;
    const y = 100 - ((v - min) / span) * 100;
    return `${x},${y}`;
  });
  return (
    <svg className="absolute inset-x-0 bottom-0 h-16 w-full opacity-[0.22]" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden>
      <defs>
        <linearGradient id="kpi-spark" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#7C3AED" stopOpacity="0.9" />
          <stop offset="100%" stopColor="#22D3EE" stopOpacity="0" />
        </linearGradient>
      </defs>
      <polyline fill="none" stroke="url(#kpi-spark)" strokeWidth="3" points={pts.join(" ")} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

export function KPITile({
  title,
  value,
  subtitle,
  icon: Icon,
  trendPct,
  sparklineValues = [],
  delay = 0,
  className,
}: KPITileProps) {
  const reduce = useReducedMotion();
  const chip =
    trendPct != null && Number.isFinite(trendPct) ? (
      <span
        className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-bold tabular-nums ${
          trendPct >= 0 ? "bg-cyan-500/15 text-cyan-300" : "bg-rose-500/15 text-rose-300"
        }`}
      >
        {trendPct >= 0 ? <TrendingUp className="h-3 w-3" aria-hidden /> : <TrendingDown className="h-3 w-3" aria-hidden />}
        {trendPct >= 0 ? "+" : ""}
        {trendPct.toFixed(1)}%
      </span>
    ) : null;

  return (
    <motion.div
      initial={reduce ? { opacity: 1 } : { opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: reduce ? 0.15 : 0.45, ease: [0.22, 1, 0.36, 1], delay: reduce ? 0 : delay }}
      className={className}
    >
      <GlassCard padding="sm" className="relative min-h-[132px] overflow-hidden border-white/[0.08]">
        {sparklineValues.length > 1 ? <Sparkline values={sparklineValues} /> : null}
        <div className="relative flex items-start justify-between gap-2">
          {Icon ? (
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-exiqo-purple to-exiqo-pink text-white shadow-md shadow-exiqo-purple/25">
              <Icon className="h-5 w-5" aria-hidden />
            </div>
          ) : (
            <span className="h-11 w-11 shrink-0" />
          )}
          {chip}
        </div>
        <p className="relative mt-3 text-[10px] font-semibold uppercase tracking-[0.16em] text-exiqo-glow/70">{title}</p>
        <p className="relative mt-1 font-heading text-2xl font-bold tabular-nums tracking-tight text-white sm:text-3xl">{value}</p>
        {subtitle ? <p className="relative mt-1 text-xs text-exiqo-glow/60">{subtitle}</p> : null}
      </GlassCard>
    </motion.div>
  );
}

export default KPITile;
