import { useCallback, useEffect, useState } from "react";
import {
  getAnomalies,
  getAnomalyStats,
  getHealthScore,
  getMonthlyTrends,
  getQuickSummary,
  getSpendingAnalysis,
  getTopMerchants,
} from "../services/api";

const DASHBOARD_KEYS = ["summary", "spending", "trends", "anomalies", "anomalyStats", "health", "merchants"];

const EMPTY_DATA = {
  summary: null,
  spending: [],
  trends: [],
  anomalies: [],
  anomalyStats: null,
  health: null,
  merchants: [],
};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export const useSmartSpend = (userId, month, year) => {
  const [data, setData] = useState(EMPTY_DATA);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [loadWarnings, setLoadWarnings] = useState([]);

  const load = useCallback(async () => {
    if (!userId) return;
    setLoading(true);
    setError("");
    setLoadWarnings([]);

    const runAll = () => Promise.allSettled([
      getQuickSummary(userId, { month, year }),
      getSpendingAnalysis(userId, month, year),
      getMonthlyTrends(userId),
      getAnomalies(userId),
      getAnomalyStats(userId),
      getHealthScore(userId, month, year),
      getTopMerchants(userId, month, year),
    ]);

    try {
      let settled = await runAll();

      // Auto-retry once after 1.8s for transient network blips (CRA proxy restart, etc.)
      const allFailed = settled.every((r) => r.status === "rejected");
      if (allFailed) {
        await sleep(1800);
        settled = await runAll();
      }

      const next = { ...EMPTY_DATA };
      const warnings = [];

      settled.forEach((result, i) => {
        const key = DASHBOARD_KEYS[i];
        if (result.status === "fulfilled") {
          const v = result.value;
          switch (key) {
            case "summary":      next.summary = v; break;
            case "spending":     next.spending = Array.isArray(v) ? v : []; break;
            case "trends":       next.trends = Array.isArray(v) ? v : []; break;
            case "anomalies":    next.anomalies = Array.isArray(v) ? v : []; break;
            case "anomalyStats": next.anomalyStats = v ?? null; break;
            case "health":       next.health = v ?? null; break;
            case "merchants":    next.merchants = Array.isArray(v) ? v : []; break;
            default: break;
          }
        } else {
          const msg = result.reason?.message || String(result.reason || "request failed");
          warnings.push(`${key}: ${msg}`);
          if (process.env.NODE_ENV === "development") {
            console.warn("[useSmartSpend] endpoint failed:", key, result.reason);
          }
        }
      });

      if (settled.every((r) => r.status === "rejected")) {
        const first = settled[0]?.reason;
        setError(first?.message || "Unable to reach server — check your connection");
      } else {
        setError("");
      }

      setLoadWarnings(warnings);
      setData(next);
    } catch (err) {
      setError(err.message || "Unable to load dashboard data");
    } finally {
      setLoading(false);
    }
  }, [userId, month, year]);

  useEffect(() => {
    load();
  }, [load]);

  // Re-fetch immediately whenever the user changes their dashboard mode from Settings.
  useEffect(() => {
    const handler = () => load();
    window.addEventListener("dashboardModeChanged", handler);
    return () => window.removeEventListener("dashboardModeChanged", handler);
  }, [load]);

  return {
    ...data,
    loading,
    error,
    loadWarnings,
    refetch: load,
  };
};

export default useSmartSpend;
