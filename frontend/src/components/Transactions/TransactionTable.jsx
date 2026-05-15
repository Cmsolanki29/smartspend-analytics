import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Download, FileText } from "lucide-react";
import { apiUtils, getTransactions } from "../../services/api";
import { EmptyState } from "../common/EmptyState";
import { ErrorCard } from "../common/ErrorCard";
import { SkeletonCard } from "../common/SkeletonCard";
import { GlassCard } from "../intro/GlassCard";

/** Labels match backend bucket names in routes/transactions.py (_CATEGORY_FILTER_BUCKETS). */
const categories = ["All", "Food & Dining", "Entertainment", "Shopping", "Travel", "Bills", "Other", "Anomalies Only"];

const csvEscape = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;

const TransactionTable = ({ userId, month, year, presentation = "default" }) => {
  const dash = presentation === "dashboard";
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("All");
  const [sortBy, setSortBy] = useState("date");
  const [page, setPage] = useState(1);
  // Bumped whenever dashboard mode changes so transactions re-fetch with new scope.
  const [modeVersion, setModeVersion] = useState(0);

  useEffect(() => {
    const handler = () => setModeVersion((v) => v + 1);
    window.addEventListener("dashboardModeChanged", handler);
    return () => window.removeEventListener("dashboardModeChanged", handler);
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const anomalyOnly = category === "Anomalies Only" ? true : undefined;
      const apiCategory = ["All", "Anomalies Only"].includes(category) ? undefined : category;
      const data = await getTransactions(userId, {
        month,
        year,
        category: apiCategory,
        anomaly_only: anomalyOnly,
        limit: 200,
      });
      setRows(data || []);
    } catch (err) {
      setError(err.message || "Unable to load transactions");
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId, month, year, category, modeVersion]);

  useEffect(() => {
    load();
  }, [load]);

  const filtered = useMemo(() => {
    let data = rows.filter((r) => String(r.merchant || "").toLowerCase().includes(search.toLowerCase()));

    if (sortBy === "amount") {
      data = [...data].sort((a, b) => Number(b.amount || 0) - Number(a.amount || 0));
    } else if (sortBy === "risk") {
      data = [...data].sort((a, b) => Number(b.risk_score || 0) - Number(a.risk_score || 0));
    } else {
      data = [...data].sort(
        (a, b) => new Date(`${b.transaction_date}T${b.transaction_time}`) - new Date(`${a.transaction_date}T${a.transaction_time}`)
      );
    }

    return data;
  }, [rows, search, sortBy]);

  const pageSize = 20;
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const pagedRows = filtered.slice((page - 1) * pageSize, page * pageSize);

  useEffect(() => {
    setPage(1);
  }, [search, sortBy, category, month, year, userId]);

  const exportCsv = () => {
    const headers = ["Date", "Merchant", "Category", "Amount", "Type", "Method", "Risk", "Risk Score"];
    const lines = [headers.join(",")];

    filtered.forEach((r) => {
      lines.push(
        [
          csvEscape(r.transaction_date),
          csvEscape(r.merchant),
          csvEscape(r.category),
          csvEscape(r.amount),
          csvEscape(r.type),
          csvEscape(r.payment_method),
          csvEscape(r.risk_level),
          csvEscape(r.risk_score),
        ].join(",")
      );
    });

    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", `transactions-user-${userId}-${month}-${year}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const tableShell = dash ? "border-white/[0.08]" : "table-wrap border-white/[0.08]";

  return (
    <GlassCard padding="md" surface="panel" className={tableShell}>
      <div className="panel-head mb-3 flex flex-col gap-3 border-b border-white/[0.06] pb-3 sm:flex-row sm:items-center sm:justify-between">
        <h3 className="font-heading text-base font-semibold text-white">Transactions</h3>
        <button
          type="button"
          className="ghost-btn inline-flex min-h-[48px] items-center gap-2 md:min-h-0"
          onClick={exportCsv}
        >
          <Download size={16} aria-hidden /> Export CSV
        </button>
      </div>

      <div className="table-controls mb-3 flex flex-col gap-3 lg:flex-row lg:flex-wrap lg:items-center">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by merchant..."
          className="min-h-[48px] w-full rounded-xl border border-white/10 bg-white/[0.04] px-4 py-2.5 text-sm text-white placeholder:text-exiqo-glow/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60 lg:max-w-xs"
        />

        <div className="filter-row flex flex-wrap gap-2">
          {categories.map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => setCategory(item)}
              className={`chip-btn min-h-[48px] md:min-h-0 ${category === item ? "active" : ""}`}
            >
              {item}
            </button>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-medium uppercase tracking-wide text-exiqo-glow/55">Sort by</span>
          <select
            aria-label="Sort transactions"
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
            className="min-h-[48px] min-w-[10.5rem] cursor-pointer rounded-xl border border-white/10 bg-[#0b1224] px-3 py-2 text-sm text-white shadow-inner shadow-black/20 md:min-h-0 [&>option]:bg-[#0b1224] [&>option]:text-white"
          >
            <option value="date">Newest date first</option>
            <option value="amount">Highest amount</option>
            <option value="risk">Highest risk score</option>
          </select>
        </div>
      </div>

      {loading ? (
        <div>
          <p className="mb-2 text-xs text-exiqo-glow/60">Loading transactions…</p>
          <SkeletonCard lines={6} height={200} />
        </div>
      ) : error ? (
        <ErrorCard message={error} onRetry={load} />
      ) : pagedRows.length === 0 ? (
        <EmptyState
          icon={<FileText className="mx-auto h-12 w-12 text-exiqo-glow/50" aria-hidden />}
          title="No transactions match"
          subtitle="Try widening filters or pick another month."
        />
      ) : (
        <>
          <div className="max-h-[min(70vh,520px)] overflow-auto rounded-xl border border-white/[0.06]">
            <table className="w-full min-w-[640px] border-collapse text-left text-sm">
              <caption className="sr-only">Transactions for selected month</caption>
              <thead className="sticky top-0 z-10 border-b border-white/[0.08] bg-exiqo-navy">
                <tr className="text-[11px] font-semibold uppercase tracking-wide text-exiqo-glow/60">
                  <th scope="col" className="px-3 py-3">Date</th>
                  <th scope="col" className="px-3 py-3">Merchant</th>
                  <th scope="col" className="px-3 py-3">Category</th>
                  <th scope="col" className="px-3 py-3">Amount</th>
                  <th scope="col" className="px-3 py-3">Source</th>
                  <th scope="col" className="px-3 py-3">Method</th>
                  <th scope="col" className="px-3 py-3">Risk</th>
                </tr>
              </thead>
              <tbody>
                {pagedRows.map((tx, idx) => (
                  <tr
                    key={tx.id}
                    className={`border-b border-white/[0.04] transition hover:bg-white/[0.05] ${
                      idx % 2 === 1 ? "bg-white/[0.02]" : ""
                    } ${String(tx.risk_level || "LOW").toLowerCase()}`}
                  >
                    <td className="whitespace-nowrap px-3 py-2.5 text-exiqo-glow/80 tabular-nums">{String(tx.transaction_date)}</td>
                    <td className="max-w-[12rem] truncate px-3 py-2.5 text-white">{tx.merchant || "—"}</td>
                    <td className="px-3 py-2.5 text-exiqo-glow/75">{tx.category || "Uncategorized"}</td>
                    <td
                      className={`px-3 py-2.5 font-heading font-semibold tabular-nums ${
                        tx.type === "CREDIT" ? "text-emerald-300" : "text-white"
                      }`}
                    >
                      {apiUtils.formatINR(tx.amount)}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2.5">
                      {tx.source_type === "credit_card" ? (
                        <span className="inline-flex items-center gap-1 rounded-full border border-violet-500/30 bg-violet-500/10 px-2 py-0.5 text-[10px] font-semibold text-violet-300">
                          💳 {tx.source_name || "Card"}
                        </span>
                      ) : tx.source_type === "bank_statement_pdf" ? (
                        <span className="inline-flex items-center gap-1 rounded-full border border-cyan-500/30 bg-cyan-500/10 px-2 py-0.5 text-[10px] font-semibold text-cyan-300">
                          🏦 {tx.source_name || "Bank"}
                        </span>
                      ) : tx.source_type ? (
                        <span className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/[0.04] px-2 py-0.5 text-[10px] text-white/50">
                          🏦 {tx.source_name || tx.source_type}
                        </span>
                      ) : (
                        <span className="text-[10px] text-white/30">Bank</span>
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-exiqo-glow/70">{tx.payment_method || "—"}</td>
                    <td className="px-3 py-2.5">
                      <span className="inline-flex items-center gap-1.5">
                        {tx.anomaly_flag ? (
                          <span className="h-full w-0.5 rounded-full bg-gradient-to-b from-rose-400 to-rose-600" aria-hidden />
                        ) : null}
                        <span className="text-xs font-medium text-exiqo-glow/85">
                          {tx.anomaly_flag ? `${tx.risk_level} · anomaly` : "Normal"}
                        </span>
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-4 flex flex-wrap items-center justify-center gap-2 sm:justify-end">
            <button
              type="button"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="min-h-[48px] rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-xs font-semibold text-white transition enabled:hover:bg-white/[0.08] disabled:opacity-40 md:min-h-0"
            >
              Prev
            </button>
            <span className="px-2 text-xs text-exiqo-glow/60 tabular-nums">
              Page {page} / {pageCount}
            </span>
            <button
              type="button"
              onClick={() => setPage((p) => Math.min(pageCount, p + 1))}
              disabled={page === pageCount}
              className="min-h-[48px] rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-xs font-semibold text-white transition enabled:hover:bg-white/[0.08] disabled:opacity-40 md:min-h-0"
            >
              Next
            </button>
          </div>
        </>
      )}
    </GlassCard>
  );
};

export default TransactionTable;
