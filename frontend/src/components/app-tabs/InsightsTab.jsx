import React, { useCallback, useEffect, useState } from "react";
import { useViewMode } from "../../context/ViewModeContext";
import { getHealthScore } from "../../services/api";
import { PageHeader } from "../Dashboard/shared/PageHeader";
import { HeroKpiTile } from "../Dashboard/shared/HeroKpiTile";
import AIInsightsPanel from "../Insights/AIInsightsPanel";
import HealthScoreGauge from "../Charts/HealthScoreGauge";
import SmartSpendChatbot from "../AIChat/SmartSpendChatbot";

const ACCENT = "#A78BFA";

/** `setActiveTab` — same tab switcher as Sidebar (CRA has no react-router-dom). */
export default function InsightsTab({ userId, month, year, setActiveTab }) {
  const { viewMode: dashboardMode } = useViewMode();

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "instant" });
  }, []);

  const [health, setHealth] = useState(null);
  const [healthLoading, setHealthLoading] = useState(true);
  const [healthError, setHealthError] = useState(false);

  const fetchHealth = useCallback(() => {
    setHealthLoading(true);
    setHealthError(false);
    return getHealthScore(userId, month, year, dashboardMode)
      .then((h) => setHealth(h))
      .catch(() => setHealthError(true))
      .finally(() => setHealthLoading(false));
  }, [userId, month, year, dashboardMode]);

  useEffect(() => {
    let cancelled = false;
    setHealthLoading(true);
    setHealthError(false);
    getHealthScore(userId, month, year, dashboardMode)
      .then((h) => {
        if (!cancelled) setHealth(h);
      })
      .catch(() => {
        if (!cancelled) setHealthError(true);
      })
      .finally(() => {
        if (!cancelled) setHealthLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [userId, month, year, dashboardMode]);

  useEffect(() => {
    const handler = () => fetchHealth();
    window.addEventListener("dashboardModeChanged", handler);
    return () => window.removeEventListener("dashboardModeChanged", handler);
  }, [fetchHealth]);

  // Re-fetch health score whenever financial data changes (new account, new EMI, new goal, etc.)
  useEffect(() => {
    const handler = () => fetchHealth();
    window.addEventListener("smartspend:health-score-changed", handler);
    window.addEventListener("smartspend:purchase-goals-changed", handler);
    window.addEventListener("smartspend-financial-sync", handler);
    return () => {
      window.removeEventListener("smartspend:health-score-changed", handler);
      window.removeEventListener("smartspend:purchase-goals-changed", handler);
      window.removeEventListener("smartspend-financial-sync", handler);
    };
  }, [fetchHealth]);

  const savingsRate =
    health?.savings_rate ?? health?.components?.savings_rate_pct ?? null;
  const insufficientData = health?.reason === "not_enough_data" || health?.score == null;
  const scoreReady = !healthLoading && !healthError && health != null && !insufficientData;
  const scoreDisplay = scoreReady ? `${health.score}/100` : insufficientData ? "—" : "—";

  const handleChatNavigate = useCallback(
    (route) => {
      const tabById = {
        emi: "emi",
        "emi-tracker": "emi",
        subscriptions: "subscriptions",
        "subscriptions-ai": "subscriptions",
        fraud: "fraud",
        fraudshield: "fraud",
        transactions: "transactions",
        dashboard: "dashboard",
        festival: "festival",
        festivals: "festival",
        "dark-patterns": "dark-patterns",
        purchase: "purchase",
        purchases: "purchase",
        insights: "insights",
        health: "insights",
        "trip-planner": "trip-planner",
      };
      if (route?.tab && tabById[route.tab] && typeof setActiveTab === "function") {
        setActiveTab(tabById[route.tab]);
        return;
      }
      const base = String(route?.path || route || "").split("?")[0].toLowerCase();
      const tabByPath = {
        "/emi-tracker": "emi",
        "/emi": "emi",
        "/subscriptions": "subscriptions",
        "/subscriptions-ai": "subscriptions",
        "/fraud-shield": "fraud",
        "/fraud": "fraud",
        "/chain-vault": "fraud-shield",
        "/transactions": "transactions",
        "/dashboard": "dashboard",
        "/festivals": "festival",
        "/festival": "festival",
        "/dark-patterns": "dark-patterns",
        "/purchases": "purchase",
        "/purchase": "purchase",
        "/insights": "insights",
        "/health": "insights",
        "/trip-planner": "trip-planner",
      };
      const tab = tabByPath[base];
      if (tab && typeof setActiveTab === "function") setActiveTab(tab);
    },
    [setActiveTab]
  );

  return (
    <div>
      <PageHeader
        eyebrow="AI INSIGHTS"
        title="Coach-grade Advice"
        subtitle="Your AI financial coach — every number grounded in your real transactions, zero hallucinations."
        accentHex={ACCENT}
        rightSlot={
          <HeroKpiTile
            label="Health score"
            value={scoreDisplay}
            caption={
              healthLoading
                ? undefined
                : insufficientData
                  ? health?.message || "Upload more statements to unlock your Health Score"
                  : savingsRate != null
                    ? `${Number(savingsRate).toFixed(1)}% savings rate this month`
                    : undefined
            }
            captionLoading={healthLoading}
            delta={
              health?.trend === "IMPROVING"
                ? 5
                : health?.trend === "DECLINING"
                  ? -5
                  : null
            }
            accentHex={ACCENT}
            loading={healthLoading}
          />
        }
      />

      <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[55%_minmax(0,1fr)]">
        <AIInsightsPanel
          userId={userId}
          month={month}
          year={year}
          scope={dashboardMode}
          presentation="default"
        />
        <HealthScoreGauge
          userId={userId}
          month={month}
          year={year}
          healthData={health || {}}
          variant="default"
          loading={healthLoading}
          loadError={healthError}
          showRecommendations
          showNarrative
          showHistory
          onRetry={fetchHealth}
        />
      </div>

      <div className="mt-8">
        <div className="mb-4">
          <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-gray-500">AI Financial Partner</p>
          <h3 className="mt-0.5 font-heading text-base font-semibold text-white">Ask your Financial Partner</h3>
          <p className="mt-1 text-sm text-white/50">
            Grounded in your real transaction data. Ask in any language.
          </p>
        </div>
        <SmartSpendChatbot
          onNavigate={handleChatNavigate}
          month={month}
          year={year}
          dashboardScope={dashboardMode}
        />
      </div>
    </div>
  );
}
