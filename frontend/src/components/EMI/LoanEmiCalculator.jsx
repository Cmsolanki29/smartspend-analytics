import React, { useEffect, useMemo, useState } from "react";
import { ArrowRight, Calculator, ShoppingBag } from "lucide-react";
import { postPurchaseAddGoal, postLoanCalculate } from "../../services/api";
import { buildLoanSummary } from "../../utils/emiCalculator";
import { inr } from "../../lib/format";
import { GlassCard } from "../intro/GlassCard";
import { SectionTitle } from "../Dashboard/shared/SectionTitle";
import { useToast } from "../common/Toast";
import { syncHealthScoreAfterMutation } from "../../utils/financialSync";

function defaultTargetDate(monthsFromNow = 12) {
  const d = new Date();
  d.setMonth(d.getMonth() + monthsFromNow);
  return d.toISOString().slice(0, 10);
}

export default function LoanEmiCalculator({ userId, onAdded }) {
  const { showToast } = useToast();
  const [productName, setProductName] = useState("Laptop");
  const [price, setPrice] = useState("60000");
  const [down, setDown] = useState("0");
  const [rate, setRate] = useState("12");
  const [tenure, setTenure] = useState("12");
  const [showSchedule, setShowSchedule] = useState(false);
  const [adding, setAdding] = useState(false);
  const [serverCheck, setServerCheck] = useState(null);

  const local = useMemo(() => {
    const p = Number(price);
    const d = Number(down);
    const r = Number(rate);
    const n = Number(tenure);
    if (!p || p <= 0 || !n) return null;
    return buildLoanSummary(p, d, r, n);
  }, [price, down, rate, tenure]);

  useEffect(() => {
    if (!userId || !local?.principal) {
      setServerCheck(null);
      return;
    }
    const t = window.setTimeout(() => {
      postLoanCalculate(userId, {
        product_name: productName,
        product_price: Number(price),
        down_payment: Number(down) || 0,
        annual_interest_rate_pct: Number(rate) || 0,
        tenure_months: Number(tenure) || 12,
      })
        .then(setServerCheck)
        .catch(() => setServerCheck(null));
    }, 400);
    return () => window.clearTimeout(t);
  }, [userId, productName, price, down, rate, tenure, local?.principal]);

  const summary = serverCheck?.emi_monthly != null ? serverCheck : local;

  const onAddToPlanner = async () => {
    if (!summary || !userId) return;
    setAdding(true);
    try {
      const months = Number(tenure) || 12;
      await postPurchaseAddGoal(userId, {
        item_name: productName.trim() || "Planned purchase",
        target_amount: Number(price),
        target_date: defaultTargetDate(months),
        category: "ELECTRONICS",
        priority: "MEDIUM",
        down_payment: Number(down) || 0,
        annual_interest_rate_pct: Number(rate) || 12,
        emi_tenure_months: months,
      });
      await syncHealthScoreAfterMutation(userId);
      showToast("Added to Purchase Planner with EMI details", "success");
      onAdded?.();
    } catch (e) {
      showToast(e instanceof Error ? e.message : "Could not add to Purchase Planner", "error");
    } finally {
      setAdding(false);
    }
  };

  return (
    <GlassCard
      surface="panel"
      padding="md"
      id="emi-loan-calculator"
      className="rounded-2xl border border-cyan-500/20 bg-white/5 backdrop-blur-2xl"
    >
      <SectionTitle
        eyebrow="Loan calculator"
        title="Calculate EMI"
        actions={
          <span className="hidden items-center gap-1 text-xs text-gray-500 sm:inline-flex">
            <Calculator className="h-3.5 w-3.5" aria-hidden />
            Reducing-balance formula
          </span>
        }
      />
      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <div className="space-y-4">
          <label className="block text-sm text-gray-400">
            Product name
            <input
              value={productName}
              onChange={(e) => setProductName(e.target.value)}
              className="mt-1 w-full rounded-xl border border-white/10 bg-[#070418]/80 px-4 py-2.5 text-white"
            />
          </label>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block text-sm text-gray-400">
              Price (₹)
              <input
                type="number"
                min="0"
                value={price}
                onChange={(e) => setPrice(e.target.value)}
                className="mt-1 w-full rounded-xl border border-white/10 bg-[#070418]/80 px-4 py-2.5 text-white tabular-nums"
              />
            </label>
            <label className="block text-sm text-gray-400">
              Down payment (₹)
              <input
                type="number"
                min="0"
                value={down}
                onChange={(e) => setDown(e.target.value)}
                className="mt-1 w-full rounded-xl border border-white/10 bg-[#070418]/80 px-4 py-2.5 text-white tabular-nums"
              />
            </label>
            <label className="block text-sm text-gray-400">
              Interest (% p.a.)
              <input
                type="number"
                min="0"
                step="0.1"
                value={rate}
                onChange={(e) => setRate(e.target.value)}
                className="mt-1 w-full rounded-xl border border-white/10 bg-[#070418]/80 px-4 py-2.5 text-white tabular-nums"
              />
            </label>
            <label className="block text-sm text-gray-400">
              Tenure (months)
              <input
                type="number"
                min="1"
                max="360"
                value={tenure}
                onChange={(e) => setTenure(e.target.value)}
                className="mt-1 w-full rounded-xl border border-white/10 bg-[#070418]/80 px-4 py-2.5 text-white tabular-nums"
              />
            </label>
          </div>
          {summary?.principal != null && Number(down) > 0 ? (
            <p className="text-xs text-cyan-200/80">
              Financed principal: {inr(summary.principal)} (after {inr(Number(down))} down payment)
            </p>
          ) : null}
        </div>

        <div className="rounded-2xl border border-white/10 bg-[#070418]/60 p-5">
          {summary ? (
            <div className="space-y-3">
              <p className="text-[10px] font-semibold uppercase tracking-widest text-gray-500">Result</p>
              <p className="font-heading text-3xl font-bold tabular-nums text-white">
                {inr(summary.emi_monthly)}
                <span className="text-lg font-medium text-gray-400">/mo</span>
              </p>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <p className="text-gray-500">Total payable</p>
                  <p className="font-semibold text-white tabular-nums">{inr(summary.total_amount_payable)}</p>
                </div>
                <div>
                  <p className="text-gray-500">Total interest</p>
                  <p className="font-semibold text-amber-200 tabular-nums">{inr(summary.total_interest)}</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setShowSchedule((v) => !v)}
                className="text-xs text-violet-300 underline hover:text-white"
              >
                {showSchedule ? "Hide" : "Show"} amortization schedule
              </button>
              {showSchedule && summary.amortization_schedule?.length ? (
                <div className="max-h-48 overflow-auto rounded-lg border border-white/10 text-xs">
                  <table className="w-full text-left">
                    <thead className="sticky top-0 bg-[#0c1022] text-gray-500">
                      <tr>
                        <th className="px-2 py-1">#</th>
                        <th className="px-2 py-1">EMI</th>
                        <th className="px-2 py-1">Principal</th>
                        <th className="px-2 py-1">Interest</th>
                        <th className="px-2 py-1">Balance</th>
                      </tr>
                    </thead>
                    <tbody>
                      {summary.amortization_schedule.map((row) => (
                        <tr key={row.month} className="border-t border-white/5 text-white/80">
                          <td className="px-2 py-1 tabular-nums">{row.month}</td>
                          <td className="px-2 py-1 tabular-nums">{inr(row.emi)}</td>
                          <td className="px-2 py-1 tabular-nums">{inr(row.principal)}</td>
                          <td className="px-2 py-1 tabular-nums">{inr(row.interest)}</td>
                          <td className="px-2 py-1 tabular-nums">{inr(row.balance)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : null}
              <button
                type="button"
                disabled={adding}
                onClick={onAddToPlanner}
                className="mt-2 flex w-full items-center justify-center gap-2 rounded-xl border border-violet-500/40 bg-violet-500/20 py-3 text-sm font-semibold text-violet-100 hover:bg-violet-500/30 disabled:opacity-50"
              >
                <ShoppingBag className="h-4 w-4" aria-hidden />
                {adding ? "Adding…" : "Add to Purchase Planner"}
                <ArrowRight className="h-4 w-4" aria-hidden />
              </button>
            </div>
          ) : (
            <p className="py-8 text-center text-sm text-gray-500">Enter price and tenure to calculate EMI.</p>
          )}
        </div>
      </div>
    </GlassCard>
  );
}
