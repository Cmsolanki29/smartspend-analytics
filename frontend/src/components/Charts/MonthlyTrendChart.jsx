import React, { useMemo } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { apiUtils } from "../../services/api";
import { EmptyState } from "../common/EmptyState";
import { GlassCard } from "../intro/GlassCard";
import { LineChart as LineChartIcon } from "lucide-react";

const monthLabel = (iso) => {
  const [y, mo] = String(iso).split("-");
  const date = new Date(Number(y), Number(mo) - 1, 1);
  return date.toLocaleDateString("en-IN", { month: "short" });
};

const axisStroke = "rgba(167,139,250,0.5)";
const gridStroke = "rgba(255,255,255,0.06)";

/** Unicode rupee avoids missing-glyph ``?`` on some system fonts for axis ticks. */
const RUPEE = "\u20B9";

const formatAxisTick = (v) => {
  const n = Number(v);
  if (!Number.isFinite(n)) return `${RUPEE}0`;
  if (n === 0) return `${RUPEE}0`;
  if (n >= 100000) return `${RUPEE}${(n / 100000).toFixed(1)}L`;
  return `${RUPEE}${Math.round(n / 1000)}k`;
};

const TrendTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) return null;
  const row = payload[0]?.payload;
  const rawMonth = row?.month;
  let title = "";
  if (rawMonth) {
    const [y, m] = String(rawMonth).split("-");
    const d = new Date(Number(y), Number(m) - 1, 1);
    title = d.toLocaleDateString("en-IN", { month: "long", year: "numeric" });
  }
  return (
    <div
      role="tooltip"
      aria-live="polite"
      className="rounded-xl border border-white/20 bg-[#0b0f1a]/95 px-3.5 py-2.5 shadow-xl backdrop-blur-md"
    >
      {title ? <div className="text-[13px] font-semibold text-white">{title}</div> : null}
      <ul className={`space-y-1.5 ${title ? "mt-2" : ""}`}>
        {payload.map((item) => (
          <li key={String(item.dataKey)} className="flex items-center justify-between gap-6 text-sm">
            <span className="font-medium" style={{ color: item.color || "#e2e8f0" }}>
              {item.name}
            </span>
            <span className="shrink-0 text-[15px] font-semibold tabular-nums text-white">{apiUtils.formatINR(item.value)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
};

/**
 * @param {{ trendsData?: Array<Record<string, unknown>>; animateOnView?: boolean }} props
 */
const MonthlyTrendChart = ({ trendsData = [], animateOnView = true }) => {
  const reduce = useReducedMotion();
  const chartData = useMemo(
    () =>
      (Array.isArray(trendsData) ? trendsData : []).map((row) => ({
        ...row,
        label: monthLabel(row.month),
      })),
    [trendsData]
  );

  const allSeriesZero = useMemo(() => {
    if (!chartData.length) return false;
    return chartData.every(
      (row) =>
        Number(row.income || 0) === 0 && Number(row.expense || 0) === 0 && Number(row.saved || 0) === 0
    );
  }, [chartData]);

  const animate = animateOnView && !reduce;

  return (
    <GlassCard padding="md" surface="panel" className="border-white/[0.08]">
      <div className="mb-3 flex items-center justify-between gap-2 border-b border-white/[0.06] pb-3">
        <h3 className="font-heading text-base font-semibold text-white">12-month spending story</h3>
      </div>

      {chartData.length === 0 ? (
        <EmptyState
          icon={<LineChartIcon className="mx-auto h-12 w-12 text-exiqo-purple/80" aria-hidden />}
          title="No trend data yet"
          subtitle="Add more monthly activity to see your curve."
        />
      ) : allSeriesZero ? (
        <EmptyState
          icon={<LineChartIcon className="mx-auto h-12 w-12 text-exiqo-purple/80" aria-hidden />}
          title="No income or debits in this window"
          subtitle="Totals are zero for every month shown. Add CREDIT transactions (e.g. salary) or DEBIT spending so the trend lines have data."
        />
      ) : (
        <>
          <div className="sr-only">
            <table>
              <caption>Monthly income, expense, and savings</caption>
              <thead>
                <tr>
                  <th scope="col">Month</th>
                  <th scope="col">Income</th>
                  <th scope="col">Expense</th>
                  <th scope="col">Saved</th>
                </tr>
              </thead>
              <tbody>
                {chartData.map((row) => (
                  <tr key={String(row.month)}>
                    <td>{String(row.month)}</td>
                    <td>{row.income}</td>
                    <td>{row.expense}</td>
                    <td>{row.saved}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <motion.div initial={reduce ? false : { opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}>
            <ResponsiveContainer width="100%" height={300}>
              <ComposedChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="expenseArea" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#7C3AED" stopOpacity={0.45} />
                    <stop offset="55%" stopColor="#EC4899" stopOpacity={0.12} />
                    <stop offset="100%" stopColor="#22D3EE" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="4 4" stroke={gridStroke} vertical={false} />
                <XAxis dataKey="label" stroke={axisStroke} tick={{ fill: "rgba(245,243,255,0.45)", fontSize: 11 }} tickLine={false} axisLine={{ stroke: "rgba(255,255,255,0.08)" }} />
                <YAxis
                  stroke={axisStroke}
                  tick={{ fill: "rgba(245,243,255,0.45)", fontSize: 11 }}
                  tickLine={false}
                  axisLine={{ stroke: "rgba(255,255,255,0.08)" }}
                  tickFormatter={formatAxisTick}
                />
                <Tooltip content={<TrendTooltip />} />
                <Area
                  type="monotone"
                  dataKey="expense"
                  name="Expense"
                  stroke="#A855F7"
                  strokeWidth={2.5}
                  fill="url(#expenseArea)"
                  isAnimationActive={animate}
                  animationDuration={1000}
                />
                <Line type="monotone" dataKey="income" name="Income" stroke="#22D3EE" strokeWidth={2} dot={false} isAnimationActive={animate} animationDuration={1000} />
                <Line type="monotone" dataKey="saved" name="Saved" stroke="#EC4899" strokeWidth={1.8} dot={false} strokeDasharray="5 5" isAnimationActive={animate} animationDuration={1000} />
              </ComposedChart>
            </ResponsiveContainer>
          </motion.div>
        </>
      )}
    </GlassCard>
  );
};

export default MonthlyTrendChart;
