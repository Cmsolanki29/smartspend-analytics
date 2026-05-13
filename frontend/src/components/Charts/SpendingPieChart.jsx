import React, { useMemo, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { PieChart as PieIcon } from "lucide-react";
import { apiUtils } from "../../services/api";
import { EmptyState } from "../common/EmptyState";
import { GlassCard } from "../intro/GlassCard";

const BRAND_SLICE_FILLS = ["#7C3AED", "#A855F7", "#EC4899", "#22D3EE", "#5B21B6", "#818CF8"];

const colorFor = (index) => BRAND_SLICE_FILLS[index % BRAND_SLICE_FILLS.length];

/** Known category → hex; other API strings fall back to `colorFor(index)` (same order as Pie cells). */
const categoryColors = {
  Groceries: "#22d3ee",
};

function sliceColor(category, index) {
  const raw = String(category ?? "").trim();
  if (raw && categoryColors[raw] != null) return categoryColors[raw];
  const matchKey = Object.keys(categoryColors).find((k) => k.toLowerCase() === raw.toLowerCase());
  if (matchKey) return categoryColors[matchKey];
  return colorFor(index);
}

const CustomTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) return null;
  const p = payload[0];
  const category = p.name ?? p.payload?.category ?? "";
  const value = p.value;
  const idx = typeof p.payload?.__sliceIndex === "number" ? p.payload.__sliceIndex : 0;
  const accent = sliceColor(category, idx);

  return (
    <div
      role="tooltip"
      aria-live="polite"
      className="rounded-xl border border-white/20 bg-[#0b0f1a]/95 px-3.5 py-2.5 shadow-xl backdrop-blur-md"
    >
      <div className="max-w-[240px]">
        <div
          className="rounded-md border-l-[3px] bg-white/10 px-2.5 py-1.5 text-xs text-white/90"
          style={{ borderLeftColor: accent }}
        >
          <div className="text-[13px] font-semibold leading-snug text-white">{String(category)}</div>
        </div>
        <div className="mt-0.5 text-[15px] font-semibold tabular-nums leading-snug text-white">{apiUtils.formatINR(value)}</div>
      </div>
    </div>
  );
};

/**
 * @param {{ spendingData?: Array<Record<string, unknown>>; month: number; year: number; prevMonthExpense?: number; animateOnView?: boolean }} props
 */
const SpendingPieChart = ({ spendingData = [], month, year, prevMonthExpense = 0, animateOnView = true }) => {
  const reduce = useReducedMotion();
  const [hovered, setHovered] = useState(null);

  const pieRows = useMemo(() => {
    const rows = Array.isArray(spendingData) ? spendingData : [];
    return rows.map((entry, idx) => ({
      ...entry,
      __sliceIndex: idx,
    }));
  }, [spendingData]);

  const total = useMemo(
    () => pieRows.reduce((acc, item) => acc + Number(item.total_amount || 0), 0),
    [pieRows]
  );

  const deltaPct = useMemo(() => {
    if (!prevMonthExpense || prevMonthExpense <= 0) return null;
    return ((total - prevMonthExpense) / prevMonthExpense) * 100;
  }, [total, prevMonthExpense]);

  const animate = animateOnView && !reduce;

  const pieActiveShape = {
    innerRadius: "58%",
    outerRadius: 108,
    stroke: "#fff",
    strokeWidth: 2,
    style: { filter: "drop-shadow(0 0 10px rgba(255,255,255,0.35))" },
  };

  return (
    <GlassCard padding="md" surface="panel" className="border-white/[0.08]">
      <div className="mb-3 flex items-center justify-between gap-2 border-b border-white/[0.06] pb-3">
        <h3 className="font-heading text-base font-semibold text-white">Spending by category</h3>
        <span className="text-[11px] font-medium text-exiqo-glow/55 tabular-nums">
          {month}/{year}
        </span>
      </div>

      {!spendingData.length ? (
        <EmptyState
          icon={<PieIcon className="mx-auto h-12 w-12 text-exiqo-pink/80" aria-hidden />}
          title="No spending data"
          subtitle="No categorized debits for this month yet."
        />
      ) : (
        <>
          <div className="sr-only">
            <table>
              <caption>Spending amounts by category</caption>
              <thead>
                <tr>
                  <th scope="col">Category</th>
                  <th scope="col">Amount</th>
                </tr>
              </thead>
              <tbody>
                {spendingData.map((entry) => (
                  <tr key={String(entry.category)}>
                    <td>{String(entry.category)}</td>
                    <td>{entry.total_amount}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <motion.div initial={reduce ? false : { opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}>
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={pieRows}
                  dataKey="total_amount"
                  nameKey="category"
                  innerRadius="58%"
                  outerRadius="88%"
                  paddingAngle={2}
                  isAnimationActive={animate}
                  animationDuration={900}
                  activeIndex={hovered != null ? hovered : undefined}
                  activeShape={pieActiveShape}
                  onMouseEnter={(_, index) => setHovered(index)}
                  onMouseLeave={() => setHovered(null)}
                >
                  {pieRows.map((entry, idx) => (
                    <Cell key={String(entry.category)} fill={sliceColor(entry.category, idx)} stroke="rgba(7,4,24,0.35)" strokeWidth={1} />
                  ))}
                </Pie>
                <Tooltip content={<CustomTooltip />} />
                <text x="50%" y="47%" textAnchor="middle" fill="rgba(167,139,250,0.75)" fontSize={11}>
                  This month
                </text>
                <text x="50%" y="55%" textAnchor="middle" fill="#f5f3ff" fontSize={18} fontWeight={700} className="tabular-nums">
                  {apiUtils.formatINR(total)}
                </text>
                {deltaPct != null && Number.isFinite(deltaPct) ? (
                  <text
                    x="50%"
                    y="62%"
                    textAnchor="middle"
                    fill={deltaPct <= 0 ? "#6ee7b7" : "#fda4af"}
                    fontSize={11}
                    fontWeight={600}
                    className="tabular-nums"
                  >
                    {deltaPct >= 0 ? "+" : ""}
                    {deltaPct.toFixed(1)}% vs last month
                  </text>
                ) : null}
              </PieChart>
            </ResponsiveContainer>
          </motion.div>
        </>
      )}
    </GlassCard>
  );
};

export default SpendingPieChart;
