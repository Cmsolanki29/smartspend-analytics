import { useCallback, useEffect, useRef, useState } from "react";
import { useViewMode } from "../context/ViewModeContext";
import {
  getAnomalies,
  getAnomalyStats,
  getHealthScore,
  getMonthlyTrends,
  getQuickSummary,
  getSpendingAnalysis,
  getTopMerchants,
  waitForBackendReady,
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

function applyResult(next, key, result) {
  if (result.status !== "fulfilled") {
    const msg = result.reason?.message || String(result.reason || "request failed");
    return { warning: `${key}: ${msg}` };
  }
  const v = result.value;
  switch (key) {
    case "summary":
      next.summary = v;
      break;
    case "spending":
      next.spending = Array.isArray(v) ? v : [];
      break;
    case "trends":
      next.trends = Array.isArray(v) ? v : [];
      break;
    case "anomalies":
      next.anomalies = Array.isArray(v) ? v : [];
      break;
    case "anomalyStats":
      next.anomalyStats = v ?? null;
      break;
    case "health":
      next.health = v ?? null;
      break;
    case "merchants":
      next.merchants = Array.isArray(v) ? v : [];
      break;
    default:
      break;
  }
  return { warning: null };
}

/** Map quick-summary health fields when /health-score is still loading. */
function healthFromSummary(summary) {
  if (!summary || summary.health_score == null) return null;
  return {
    score: summary.health_score,
    grade: summary.health_grade,
    trend: summary.health_trend || "STABLE",
    health_band: summary.health_band,
    health_label: summary.health_label,
    recommendations: [],
    components: {
      month_net_inr: summary.this_month_saved,
      ytd_saved_inr: summary.ytd_saved_inr,
    },
    savings_rate: summary.savings_rate,
  };
}

export const useSmartSpend = (userId, month, year) => {
  const { viewMode } = useViewMode();
  const [data, setData] = useState(EMPTY_DATA);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [loadWarnings, setLoadWarnings] = useState([]);
  const loadGen = useRef(0);

  const load = useCallback(async () => {
    if (!userId) return;
    const gen = ++loadGen.current;
    setLoading(true);
    setError("");
    setLoadWarnings([]);

    await waitForBackendReady(25000);

    const next = { ...EMPTY_DATA };
    const warnings = [];

    const runWave = async (calls) => {
      const settled = await Promise.allSettled(calls.map((c) => c.fn()));
      settled.forEach((result, i) => {
        const { key } = calls[i];
        const out = applyResult(next, key, result);
        if (out.warning) warnings.push(out.warning);
      });
      return settled;
    };

    try {
      // Wave 1 — KPIs + charts (avoid hammering DB with 7 parallel heavy queries)
      await runWave([
        {
          key: "summary",
          fn: () => getQuickSummary(userId, { month, year, scope: viewMode }),
        },
        {
          key: "trends",
          fn: () => getMonthlyTrends(userId, viewMode),
        },
        {
          key: "spending",
          fn: () => getSpendingAnalysis(userId, month, year, viewMode),
        },
      ]);

      if (gen !== loadGen.current) return;

      if (next.summary && !next.health) {
        next.health = healthFromSummary(next.summary);
      }

      setData({ ...next });
      setLoadWarnings([...warnings]);
      setLoading(false);

      // Wave 2 — secondary widgets (UI already visible)
      await runWave([
        { key: "anomalies", fn: () => getAnomalies(userId, null, viewMode) },
        { key: "anomalyStats", fn: () => getAnomalyStats(userId, viewMode) },
        { key: "health", fn: () => getHealthScore(userId, month, year, viewMode) },
        { key: "merchants", fn: () => getTopMerchants(userId, month, year, viewMode) },
      ]);

      if (gen !== loadGen.current) return;

      if (!next.health && next.summary) {
        next.health = healthFromSummary(next.summary);
      }

      const hasAnyKpi =
        next.summary != null ||
        (Array.isArray(next.trends) && next.trends.length > 0) ||
        (Array.isArray(next.spending) && next.spending.length > 0);
      const wave1Failed = warnings.filter((w) =>
        /^(summary|trends|spending):/.test(w)
      ).length;
      const backendDown = wave1Failed >= 3 && !hasAnyKpi;
      if (backendDown) {
        setError(
          "Dashboard data could not load. Run .\\start-dev.ps1, wait until the backend is healthy, then click Retry."
        );
      } else {
        setError("");
      }

      let finalWarnings = warnings.filter((w) => !w.includes("anomalyStats"));
      if (!hasAnyKpi && !backendDown && warnings.length > 0) {
        finalWarnings = [
          ...finalWarnings,
          "No data for this month yet — pick another month or upload a statement.",
        ];
      }
      setLoadWarnings(finalWarnings);
      setData({ ...next });
    } catch (err) {
      if (gen !== loadGen.current) return;
      setError(err?.message || "Unable to load dashboard data.");
    } finally {
      if (gen === loadGen.current) setLoading(false);
    }
  }, [userId, month, year, viewMode]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    let debounceId = null;
    const handler = (ev) => {
      const uid = Number(ev?.detail?.user_id);
      if (uid && uid !== Number(userId)) return;
      window.clearTimeout(debounceId);
      debounceId = window.setTimeout(() => load(), 2000);
    };
    const onHealth = (ev) => {
      const d = ev?.detail;
      if (d?.userId != null && Number(d.userId) !== Number(userId)) return;
      if (d?.score != null) {
        setData((prev) => ({
          ...prev,
          health: {
            ...(prev.health || {}),
            score: d.score,
            grade: d.grade ?? prev.health?.grade,
            trend: d.trend ?? prev.health?.trend,
            health_band: d.health_band ?? prev.health?.health_band,
            health_label: d.health_label ?? prev.health?.health_label,
          },
        }));
      }
      window.clearTimeout(debounceId);
      debounceId = window.setTimeout(() => load(), 800);
    };
    window.addEventListener("smartspend:data-updated", handler);
    window.addEventListener("smartspend:health-score-changed", onHealth);
    window.addEventListener("smartspend-financial-sync", handler);
    return () => {
      window.clearTimeout(debounceId);
      window.removeEventListener("smartspend:data-updated", handler);
      window.removeEventListener("smartspend:health-score-changed", onHealth);
      window.removeEventListener("smartspend-financial-sync", handler);
    };
  }, [userId, load]);

  return {
    ...data,
    loading,
    error,
    loadWarnings,
    refetch: load,
  };
};

export default useSmartSpend;
