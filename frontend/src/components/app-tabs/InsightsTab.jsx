import React, { useCallback, useEffect, useState } from "react";
import { getHealthScore, getQuickSummary } from "../../services/api";
import { PageHeader } from "../Dashboard/shared/PageHeader";
import { HeroKpiTile } from "../Dashboard/shared/HeroKpiTile";
import AIInsightsPanel from "../Insights/AIInsightsPanel";
import HealthScoreGauge from "../Charts/HealthScoreGauge";
import { GlassCard } from "../intro/GlassCard";
import SmartSpendChatbot from "../AIChat/SmartSpendChatbot";

const ACCENT = "#A78BFA";

/** `setActiveTab` — same tab switcher as Sidebar (CRA has no react-router-dom). */
export default function InsightsTab({ userId, month, year, setActiveTab }) {
  // Always land at the top of the page when this tab is entered.
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "instant" });
  }, []);

  const [health, setHealth] = useState(null);
  const [healthLoading, setHealthLoading] = useState(true);
  const [healthError, setHealthError] = useState(false);
  const [summary, setSummary] = useState(null);
  const [summaryLoading, setSummaryLoading] = useState(true);

  const handleChatNavigate = useCallback(
    (path) => {
      const base = String(path || "").split("?")[0].toLowerCase();
      const tabByPath = {
        // explicit paths from backend system prompt
        "/emi-tracker": "emi",
        "/emi": "emi",
        "/subscriptions": "subscriptions",
        "/subscriptions-ai": "subscriptions",
        "/fraud-shield": "fraud",
        "/fraud": "fraud",
        "/transactions": "transactions",
        "/dashboard": "dashboard",
        "/festivals": "festival",
        "/festival": "festival",
        "/dark-patterns": "dark-patterns",
        "/purchases": "purchase",
        "/purchase": "purchase",
        "/insights": "insights",
        "/health": "insights",
      };
      const tab = tabByPath[base];
      if (tab && typeof setActiveTab === "function") setActiveTab(tab);
    },
    [setActiveTab]
  );

  useEffect(() => {
    let cancelled = false;
    setHealthLoading(true);
    setHealthError(false);
    getHealthScore(userId, month, year)
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
  }, [userId, month, year]);

  useEffect(() => {
    let cancelled = false;
    setSummaryLoading(true);
    getQuickSummary(userId, { month, year })
      .then((s) => {
        if (!cancelled) setSummary(s);
      })
      .catch(() => {
        if (!cancelled) setSummary(null);
      })
      .finally(() => {
        if (!cancelled) setSummaryLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [userId, month, year]);

  const refetchAll = useCallback(() => {
    setHealthLoading(true);
    setHealthError(false);
    getHealthScore(userId, month, year)
      .then((h) => setHealth(h))
      .catch(() => setHealthError(true))
      .finally(() => setHealthLoading(false));
    setSummaryLoading(true);
    getQuickSummary(userId, { month, year })
      .then((s) => setSummary(s))
      .catch(() => setSummary(null))
      .finally(() => setSummaryLoading(false));
  }, [userId, month, year]);

  useEffect(() => {
    const handler = () => refetchAll();
    window.addEventListener("dashboardModeChanged", handler);
    return () => window.removeEventListener("dashboardModeChanged", handler);
  }, [refetchAll]);

  const savingsRate =
    summary?.savings_rate ?? health?.savings_rate ?? health?.components?.savings_rate_pct ?? null;
  const scoreReady = !healthLoading && !healthError && health != null;
  const scoreDisplay = scoreReady && health.score != null ? `${health.score}/100` : "—";

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
              summaryLoading || healthLoading
                ? undefined
                : savingsRate != null
                  ? `${savingsRate.toFixed(1)}% savings rate this month`
                  : undefined
            }
            captionLoading={summaryLoading || healthLoading}
            delta={savingsRate != null ? savingsRate - 10 : null}
            accentHex={ACCENT}
            loading={healthLoading}
          />
        }
      />

      <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[55%_minmax(0,1fr)]">
        <AIInsightsPanel userId={userId} month={month} year={year} presentation="default" />
        <HealthScoreGauge
          healthData={health || {}}
          variant="default"
          loading={healthLoading}
          loadError={healthError}
          onRetry={() => {
            setHealthLoading(true);
            setHealthError(false);
            getHealthScore(userId, month, year)
              .then(setHealth)
              .catch(() => setHealthError(true))
              .finally(() => setHealthLoading(false));
          }}
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
        <SmartSpendChatbot onNavigate={handleChatNavigate} />
      </div>
    </div>
  );
}
