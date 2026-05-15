import React, { useEffect, useState } from "react";
import { getTransactionSummary, getAnomalyStats } from "../../services/api";
import { PageHeader } from "../Dashboard/shared/PageHeader";
import { HeroKpiTile } from "../Dashboard/shared/HeroKpiTile";
import TransactionTable from "../Transactions/TransactionTable";

const ACCENT = "#22D3EE";

export default function TransactionsTab({ userId, month, year }) {
  const [summary, setSummary] = useState(null);
  const [anomalies, setAnomalies] = useState(null);
  const [loading, setLoading] = useState(true);
  // Bumped when dashboardModeChanged fires — causes useEffect below to re-run.
  const [modeVersion, setModeVersion] = useState(0);

  useEffect(() => {
    const handler = () => setModeVersion((v) => v + 1);
    window.addEventListener("dashboardModeChanged", handler);
    return () => window.removeEventListener("dashboardModeChanged", handler);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.allSettled([
      getTransactionSummary(userId, { month, year }),
      getAnomalyStats(userId),
    ]).then(([sumRes, anomRes]) => {
      if (cancelled) return;
      setSummary(sumRes.status === "fulfilled" ? sumRes.value : null);
      setAnomalies(anomRes.status === "fulfilled" ? anomRes.value : null);
      setLoading(false);
    });
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId, month, year, modeVersion]);

  const count = summary?.transaction_count ?? summary?.total_count ?? summary?.count ?? 0;
  const anomCount =
    summary?.anomalies_flagged ??
    summary?.flagged_count ??
    anomalies?.total_anomalies ??
    anomalies?.flagged_count ??
    0;
  const fraudCount = summary?.fraud_blocked ?? 0;

  return (
    <div>
      <PageHeader
        eyebrow="TRANSACTIONS"
        title="Your Money Story"
        subtitle="Every rupee in and out, filtered by AI — anomalies flagged, patterns surfaced."
        accentHex={ACCENT}
        rightSlot={
          <HeroKpiTile
            label="Analysed this month"
            value={count.toLocaleString("en-IN")}
            caption={`${anomCount} flagged by AI · ${fraudCount} blocked`}
            accentHex={ACCENT}
            loading={loading}
          />
        }
      />
      <TransactionTable userId={userId} month={month} year={year} />
    </div>
  );
}
