import React, { useMemo, useState } from "react";
import { AlertTriangle, ChevronRight, Eye, ShieldCheck } from "lucide-react";
import { apiUtils } from "../../services/api";
import { EmptyState } from "../common/EmptyState";
import { GlassCard } from "../intro/GlassCard";
import AnomalyModal from "./AnomalyModal";

const dotClass = (risk) => {
  const r = String(risk || "LOW").toUpperCase();
  if (r === "CRITICAL") return "bg-rose-500 shadow-[0_0_12px_rgba(244,63,94,0.55)]";
  if (r === "HIGH") return "bg-orange-400 shadow-[0_0_10px_rgba(251,146,60,0.45)]";
  if (r === "MEDIUM") return "bg-amber-400";
  return "bg-emerald-400/80";
};

const AnomalyList = ({ anomalies = [], userId, compact = false }) => {
  const [severityFilter, setSeverityFilter] = useState("ALL");
  const [sortBy, setSortBy] = useState("risk");
  const [visible, setVisible] = useState(10);
  const [selected, setSelected] = useState(null);

  const filtered = useMemo(() => {
    let list = [...(anomalies || [])];

    if (!compact && severityFilter !== "ALL") {
      list = list.filter((a) => String(a.risk_level).toUpperCase() === severityFilter);
    }

    if (sortBy === "date") {
      list.sort((a, b) => new Date(b.transaction_date) - new Date(a.transaction_date));
    } else if (sortBy === "amount") {
      list.sort((a, b) => Number(b.amount || 0) - Number(a.amount || 0));
    } else {
      list.sort((a, b) => Number(b.risk_score || 0) - Number(a.risk_score || 0));
    }

    return list;
  }, [anomalies, severityFilter, sortBy, compact]);

  const limit = compact ? 5 : visible;
  const visibleRows = filtered.slice(0, limit);

  const body =
    visibleRows.length === 0 ? (
      <EmptyState
        icon={<ShieldCheck className="mx-auto h-14 w-14 text-emerald-400/90" aria-hidden />}
        title={anomalies.length === 0 ? "No suspicious transactions this period" : "No rows match this filter"}
        subtitle={
          anomalies.length === 0
            ? "Isolation Forest did not flag anomalies for the current view — great news."
            : "Try another severity or sort option."
        }
      />
    ) : (
      <>
        <div className="space-y-2">
          {visibleRows.map((a) => (
            <article
              key={a.transaction_id}
              className={`flex flex-col gap-2 rounded-xl border border-white/[0.08] bg-white/[0.03] p-3 transition hover:bg-white/[0.06] ${
                ["CRITICAL", "HIGH"].includes(String(a.risk_level).toUpperCase()) ? "border-l-2 border-l-rose-500/90" : ""
              }`}
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${dotClass(a.risk_level)}`} title={a.risk_level} />
                <strong className="min-w-0 flex-1 truncate text-sm text-white">{a.merchant || "Unknown merchant"}</strong>
                <span className="font-heading text-sm font-bold tabular-nums text-white">{apiUtils.formatINR(a.amount)}</span>
              </div>
              <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-exiqo-glow/55">
                <span className="tabular-nums">{String(a.transaction_date)}</span>
                <span className="rounded-md bg-white/[0.06] px-2 py-0.5 text-[10px] font-semibold uppercase text-exiqo-glow/80">
                  {a.risk_level}
                </span>
              </div>
              <p className="line-clamp-2 text-xs text-exiqo-glow/70">{a.reason}</p>
              <div className="flex items-center justify-between">
                <span className="text-[11px] text-exiqo-glow/50 tabular-nums">Risk {a.risk_score}</span>
                <button
                  type="button"
                  onClick={() => setSelected(a)}
                  className="inline-flex min-h-[48px] items-center gap-1 text-xs font-semibold text-cyan-300 transition hover:text-cyan-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60 md:min-h-0"
                >
                  AI explained
                  <ChevronRight className="h-3.5 w-3.5" aria-hidden />
                  <Eye className="h-3.5 w-3.5" aria-hidden />
                </button>
              </div>
            </article>
          ))}
        </div>

        {!compact && filtered.length > visible ? (
          <button className="ghost-btn mt-3 inline-flex min-h-[48px] items-center gap-2 md:min-h-0" type="button" onClick={() => setVisible((v) => v + 10)}>
            <AlertTriangle size={16} aria-hidden />
            Load more
          </button>
        ) : null}
      </>
    );

  return (
    <>
      {compact ? (
        <GlassCard padding="md" surface="panel" className="border-white/[0.08]">
          <div className="mb-3 border-b border-white/[0.06] pb-3">
            <h3 className="font-heading text-base font-semibold text-white">Top anomalies</h3>
            <p className="text-xs text-exiqo-glow/60">{filtered.length} flagged in view</p>
          </div>
          {body}
        </GlassCard>
      ) : (
        <GlassCard padding="md" surface="panel" className="anomaly-card-wrap border-white/[0.08]">
          <div className="panel-head mb-3 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <h3 className="flex items-center gap-2 font-heading text-base font-semibold text-white">
                <AlertTriangle className="h-5 w-5 text-exiqo-pink" aria-hidden />
                Suspicious transactions
              </h3>
              <p className="text-xs text-exiqo-glow/60">{filtered.length} transactions flagged</p>
            </div>

            <div className="filter-row flex flex-wrap gap-2">
              {["ALL", "CRITICAL", "HIGH", "MEDIUM"].map((risk) => (
                <button
                  type="button"
                  key={risk}
                  onClick={() => setSeverityFilter(risk)}
                  className={`chip-btn min-h-[48px] md:min-h-0 ${severityFilter === risk ? "active" : ""}`}
                >
                  {risk}
                </button>
              ))}

              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value)}
                className="min-h-[48px] rounded-lg border border-white/10 bg-white/[0.04] px-2 text-sm text-white md:min-h-0"
              >
                <option value="risk">Risk Score</option>
                <option value="date">Date</option>
                <option value="amount">Amount</option>
              </select>
            </div>
          </div>
          {body}
        </GlassCard>
      )}

      <AnomalyModal isOpen={Boolean(selected)} onClose={() => setSelected(null)} transaction={selected} userId={userId} />
    </>
  );
};

export default AnomalyList;
