import React, { useEffect, useState } from "react";
import { getHealthScore, getQuickSummary } from "../../services/api";
import { PageHeader } from "../Dashboard/shared/PageHeader";
import { HeroKpiTile } from "../Dashboard/shared/HeroKpiTile";
import AIInsightsPanel from "../Insights/AIInsightsPanel";
import HealthScoreGauge from "../Charts/HealthScoreGauge";
import ScenarioSimulator from "../Simulator/ScenarioSimulator";
import { GlassCard } from "../intro/GlassCard";
import { SkeletonCard } from "../common/SkeletonCard";

const ACCENT = "#A78BFA";

export default function InsightsTab({ userId, month, year }) {
  const [health, setHealth] = useState(null);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.allSettled([
      getHealthScore(userId, month, year),
      getQuickSummary(userId, { month, year }),
    ]).then(([hRes, sRes]) => {
      if (cancelled) return;
      setHealth(hRes.status === "fulfilled" ? hRes.value : null);
      setSummary(sRes.status === "fulfilled" ? sRes.value : null);
      setLoading(false);
    });
    return () => { cancelled = true; };
  }, [userId, month, year]);

  const savingsRate = summary?.savings_rate ?? health?.savings_rate ?? null;
  const score       = health?.score ?? health?.health_score ?? 0;

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
            value={score ? `${score}/100` : "—"}
            caption={savingsRate != null ? `${savingsRate.toFixed(1)}% savings rate this month` : "Loading..."}
            delta={savingsRate != null ? savingsRate - 10 : null}
            accentHex={ACCENT}
            loading={loading}
          />
        }
      />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <AIInsightsPanel userId={userId} month={month} year={year} presentation="default" />
        <GlassCard padding="md" className="border-white/[0.08]">
          {loading ? (
            <SkeletonCard lines={4} height={200} />
          ) : (
            <HealthScoreGauge healthData={health || {}} variant="default" />
          )}
        </GlassCard>
      </div>

      <div className="mt-4">
        <ScenarioSimulator userId={userId} month={month} year={year} presentation="compact" />
      </div>
    </div>
  );
}
