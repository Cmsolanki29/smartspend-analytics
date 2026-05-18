import React, { forwardRef } from "react";
import { motion, useReducedMotion } from "framer-motion";
import type { FlaggedTransaction } from "./mockData";
import { CHAINVAULT } from "./chainVaultTheme";

function riskScoreClass(score: number) {
  if (score >= 90) return "text-rose-400";
  if (score >= 80) return "text-amber-300";
  return "text-sky-400";
}

type Props = {
  rows: FlaggedTransaction[];
  premium?: boolean;
};

const TransactionTable = forwardRef<HTMLElement, Props>(function TransactionTable({ rows, premium }, ref) {
  const reduce = useReducedMotion();

  return (
    <motion.section
      ref={ref}
      className="mt-6 rounded-xl border p-6"
      style={{
        background: premium ? CHAINVAULT.cardBgElevated : "#1a1d27",
        borderColor: premium ? CHAINVAULT.goldBorderSoft : "rgba(255,255,255,0.06)",
        boxShadow: premium ? `0 0 48px -20px ${CHAINVAULT.goldGlow}` : undefined,
      }}
      initial={reduce ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: 0.12, ease: [0.22, 1, 0.36, 1] }}
    >
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-white">Recent flagged transactions</h2>
          <p className="mt-1 text-sm" style={{ color: premium ? CHAINVAULT.muted : "#8b8fa8" }}>
            Live queue · highest risk first
          </p>
        </div>
        <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs font-semibold text-emerald-300">
          {rows.length} in review
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] border-collapse text-left text-sm">
          <thead>
            <tr
              className="border-b border-white/[0.06] text-[11px] font-semibold uppercase tracking-[0.12em]"
              style={{ color: premium ? CHAINVAULT.muted : "#8b8fa8" }}
            >
              <th className="pb-3 pr-4 font-semibold">Time</th>
              <th className="pb-3 pr-4 font-semibold">Txn ID</th>
              <th className="pb-3 pr-4 font-semibold">From</th>
              <th className="pb-3 pr-4 font-semibold">To</th>
              <th className="pb-3 pr-4 font-semibold">Amount</th>
              <th className="pb-3 pr-4 font-semibold">Typology</th>
              <th className="pb-3 font-semibold text-right">Risk Score</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.txnId} className="border-b border-white/[0.04] transition hover:bg-white/[0.02]">
                <td className="py-3.5 pr-4 tabular-nums text-gray-400">{row.time}</td>
                <td className="py-3.5 pr-4 font-mono text-xs text-gray-300">{row.txnId}</td>
                <td className="py-3.5 pr-4 text-white">{row.from}</td>
                <td className="py-3.5 pr-4 text-gray-300">{row.to}</td>
                <td className="py-3.5 pr-4 font-semibold tabular-nums text-white">{row.amount}</td>
                <td className="py-3.5 pr-4">
                  <span className="inline-block rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-xs font-medium text-amber-200">
                    {row.typology}
                  </span>
                </td>
                <td className={`py-3.5 text-right text-base font-bold tabular-nums ${riskScoreClass(row.riskScore)}`}>
                  {row.riskScore}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </motion.section>
  );
});

export default TransactionTable;
