import React, { useCallback, useEffect, useState } from "react";
import { RefreshCw, Search } from "lucide-react";
import { useViewMode } from "../../context/ViewModeContext";
import { getUserInvestigations } from "../../services/api";
import { fraudAlertDisplayLabel } from "../../utils/fraudLabels";
import { ErrorCard } from "../common/ErrorCard";
import { SkeletonCard } from "../common/SkeletonCard";
import { fmtCurrency, fmtRelativeTime } from "../../utils/risk/formatters";

export default function InvestigationList({ userId }) {
  const { viewMode } = useViewMode();
  const [items, setItems] = useState([]);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!userId) {
      setItems([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const data = await getUserInvestigations(userId, viewMode);
      setItems(Array.isArray(data?.investigations) ? data.investigations : []);
      setMessage(data?.message || "");
    } catch (e) {
      setError(e?.message || "Failed to load investigations");
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [userId, viewMode]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const handler = () => load();
    window.addEventListener("smartspend:data-updated", handler);
    window.addEventListener("dashboardModeChanged", handler);
    return () => {
      window.removeEventListener("smartspend:data-updated", handler);
      window.removeEventListener("dashboardModeChanged", handler);
    };
  }, [load]);

  if (loading && !items.length) {
    return <SkeletonCard lines={4} height={140} />;
  }
  if (error && !items.length) {
    return <ErrorCard message={error} onRetry={load} />;
  }
  if (!items.length) {
    return (
      <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-8 text-center">
        <Search className="mx-auto mb-3 h-10 w-10 text-gray-500" aria-hidden />
        <p className="text-sm font-medium text-white/70">
          {message || "No investigations in this view"}
        </p>
        <p className="mt-2 text-xs text-gray-500">
          Only transactions flagged as unusual with risk score 50+ appear here.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <button
          type="button"
          onClick={load}
          className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-1.5 text-xs text-gray-300 hover:bg-white/10"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Refresh
        </button>
      </div>
      {items.map((row) => {
        const label =
          row.display_label ||
          fraudAlertDisplayLabel(row.alert_type, row.risk_score);
        const badgeClass =
          Number(row.risk_score) >= 70
            ? "bg-red-900/50 text-red-200 border-red-500/40"
            : "bg-yellow-900/40 text-yellow-200 border-yellow-500/35";
        return (
          <article
            key={row.transaction_id}
            className="rounded-2xl border border-white/10 bg-white/[0.03] p-4"
          >
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <p className="font-semibold text-white">{row.merchant || "Unknown"}</p>
                <p className="text-xs text-gray-500">
                  {fmtCurrency(row.amount)} ·{" "}
                  {row.transaction_date
                    ? fmtRelativeTime(row.transaction_date)
                    : "—"}
                </p>
              </div>
              <span
                className={`rounded-full border px-2.5 py-0.5 text-[10px] font-bold uppercase ${badgeClass}`}
              >
                {label}
              </span>
            </div>
            <p className="mt-2 text-xs text-gray-400">
              Risk {row.risk_score}/100 · {row.anomaly_reason || "Statistical anomaly"}
            </p>
          </article>
        );
      })}
    </div>
  );
}
