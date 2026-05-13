import React from "react";
import { motion, useReducedMotion } from "framer-motion";
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import { RadialBar, RadialBarChart, ResponsiveContainer } from "recharts";
import { GlassCard } from "../intro/GlassCard";

const gradeColor = {
  A: "#22c55e",
  B: "#3b82f6",
  C: "#f59e0b",
  D: "#f97316",
  F: "#ef4444",
};

const TrendBadge = ({ trend }) => {
  const up = trend === "IMPROVING";
  const down = trend === "DECLINING";
  const Icon = up ? ArrowUpRight : down ? ArrowDownRight : Minus;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/[0.06] px-2.5 py-1 text-[11px] font-semibold text-exiqo-glow/90 ${
        up ? "text-emerald-300" : down ? "text-rose-300" : ""
      }`}
    >
      <Icon className="h-3.5 w-3.5" aria-hidden />
      {trend || "STABLE"}
    </span>
  );
};

const Breakdown = ({ label, value, max }) => {
  const ratio = Math.max(0, Math.min(100, (Number(value || 0) / max) * 100));
  return (
    <div className="space-y-1.5">
      <div className="flex justify-between text-[11px] text-exiqo-glow/75">
        <span>{label}</span>
        <span className="tabular-nums text-white/90">
          {value}/{max}
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
        <motion.div
          className="h-full rounded-full bg-gradient-to-r from-exiqo-purple via-exiqo-pink to-[#22D3EE]"
          initial={{ width: 0 }}
          animate={{ width: `${ratio}%` }}
          transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
        />
      </div>
    </div>
  );
};

/**
 * @param {{ healthData?: Record<string, unknown>; narration?: string; variant?: "default" | "hero" }}=} props
 */
const HealthScoreGauge = ({ healthData = {}, narration, variant = "default" }) => {
  const reduce = useReducedMotion();
  const score = Number(healthData.score || 0);
  const grade = healthData.grade || "F";
  const comp = healthData.components || {};
  const trend = healthData.trend || "STABLE";

  const chartData = [{ name: "score", value: score, fill: "url(#healthScoreBrandGrad)" }];

  const gauge = (
    <div className="relative mx-auto w-full max-w-[280px]">
      <ResponsiveContainer width="100%" height={variant === "hero" ? 220 : 240}>
        <RadialBarChart
          innerRadius="72%"
          outerRadius="100%"
          cx="50%"
          cy="70%"
          startAngle={180}
          endAngle={0}
          data={chartData}
          barSize={variant === "hero" ? 18 : 16}
        >
          <defs>
            <linearGradient id="healthScoreBrandGrad" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor="#7C3AED" />
              <stop offset="45%" stopColor="#A855F7" />
              <stop offset="78%" stopColor="#EC4899" />
              <stop offset="100%" stopColor="#22D3EE" />
            </linearGradient>
          </defs>
          <RadialBar
            minAngle={2}
            background={{ fill: "rgba(255,255,255,0.06)" }}
            clockWise
            dataKey="value"
            cornerRadius={10}
            isAnimationActive={!reduce}
            animationDuration={reduce ? 0 : 1200}
            animationEasing="ease-out"
          />
        </RadialBarChart>
      </ResponsiveContainer>
      <div className="absolute inset-0 flex flex-col items-center justify-end pb-2 text-center" style={{ paddingBottom: variant === "hero" ? "2.25rem" : "2rem" }}>
        <p
          className={`font-heading font-bold tabular-nums tracking-tight ${
            variant === "hero" ? "text-5xl sm:text-6xl" : "text-4xl"
          } bg-gradient-to-br from-white via-exiqo-glow to-exiqo-pink bg-clip-text text-transparent`}
        >
          {score}
        </p>
        <p className="text-[11px] font-medium text-exiqo-glow/60">/ 100</p>
        <span
          className="mt-1 rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white"
          style={{ background: gradeColor[grade] || "#ef4444" }}
        >
          {grade}
        </span>
      </div>
    </div>
  );

  if (variant === "hero") {
    return (
      <GlassCard padding="md" surface="panel" className="relative overflow-hidden border-white/[0.1]">
        <div className="mb-2 flex items-center justify-between gap-2">
          <h3 className="font-heading text-sm font-semibold text-white sm:text-base">Financial health</h3>
          <TrendBadge trend={trend} />
        </div>
        {gauge}
        {narration ? (
          <p className="mt-2 text-center text-sm leading-relaxed text-exiqo-glow/80 line-clamp-4">{narration}</p>
        ) : null}
      </GlassCard>
    );
  }

  return (
    <GlassCard padding="md" surface="panel" className="border-white/[0.08]">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="font-heading text-base font-semibold text-white">Financial Health</h3>
        <TrendBadge trend={trend} />
      </div>
      {gauge}
      <div className="mt-4 space-y-3 border-t border-white/[0.06] pt-4">
        <Breakdown label="Savings Rate" value={comp.savings_points || 0} max={30} />
        <Breakdown label="Security" value={comp.anomaly_points || 0} max={20} />
        <Breakdown label="Expense Ratio" value={comp.expense_points || 0} max={25} />
        <Breakdown label="Consistency" value={comp.consistency_points || 0} max={15} />
        <Breakdown label="Diversity" value={comp.diversity_points || 0} max={10} />
      </div>
    </GlassCard>
  );
};

export default HealthScoreGauge;
