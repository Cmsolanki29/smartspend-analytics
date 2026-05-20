/**
 * Subscription Intelligence — typed wrappers around `api.js` Phase 3 routes.
 * Uses the shared axios client (401 refresh, friendly errors).
 */

import {
  getSubscriptionIntelAiSummary,
  getSubscriptionIntelHealth,
  getSubscriptionIntelInsightsFeed,
  getSubscriptionIntelMigrationsCategory,
  getSubscriptionIntelSavings,
  getSubscriptionIntelVerdictsSnapshot,
  patchSubscriptionInsightRead,
  postSubscriptionIntelMigrationsPersist,
  postSubscriptionIntelRemindersScheduleUpcoming,
} from "./api";

export type VerdictBucket = "thriving" | "declining" | "dormant" | "upgrade_recommended";

export type VerdictRow = {
  subscription_id: number;
  subscription_name: string;
  verdict: string;
  reasoning: string;
  confidence_score: number;
  monthly_cost: number;
  current_usage_hours?: number;
  previous_usage_hours?: number;
  usage_change_percentage?: number;
};

export type VerdictBuckets = Record<VerdictBucket, VerdictRow[]>;

export type CategoryMigration = {
  insight_type: string;
  primary_subscription_id: number;
  secondary_subscription_id: number;
  title: string;
  description: string;
  recommendation: string;
  potential_savings_monthly: number;
  potential_savings_yearly: number;
  confidence_score: number;
};

export type AISummarySummary = {
  subscriptions_tracked: number;
  thriving_count: number;
  declining_count: number;
  dormant_count: number;
  upgrade_recommended_count: number;
  at_risk_count: number;
  verdict_monthly_waste_sum_inr: number;
  verdict_yearly_waste_sum_inr: number;
  migrations_detected: number;
  savings_amount_saved_ytd_inr: number;
  subscriptions_cancelled_ytd: number;
};

export type AISummaryBundle = {
  verdicts: VerdictBuckets;
  migrations: CategoryMigration[];
  summary: AISummarySummary;
};

export type IntelligenceInsight = {
  id: number;
  subscription_id: number | null;
  insight_type: string;
  title: string;
  body: string;
  priority: number;
  read_at: string | null;
  created_at: string | null;
};

export type SavingsPayload = {
  success: boolean;
  at_risk_subscriptions?: number;
  this_month: {
    subscriptions_cancelled: number;
    amount_saved_inr: number;
    waste_prevented_monthly_inr: number;
    waste_prevented_yearly_inr: number;
    total_impact_monthly_inr?: number;
  };
  this_year: {
    subscriptions_cancelled: number;
    amount_saved_inr: number;
    waste_prevented_yearly_inr: number;
    total_impact_yearly_inr?: number;
  };
  all_time: {
    subscriptions_cancelled: number;
    amount_saved_inr: number;
  };
};

export type HealthPayload = {
  ok: boolean;
  service: string;
  phase?: string;
};

export async function checkHealth(): Promise<HealthPayload> {
  return getSubscriptionIntelHealth() as Promise<HealthPayload>;
}

export async function getAISummary(
  userId: number
): Promise<AISummaryBundle & { success: boolean }> {
  return getSubscriptionIntelAiSummary(userId) as Promise<
    AISummaryBundle & { success: boolean }
  >;
}

export async function getVerdictSnapshot(userId: number): Promise<{
  success: boolean;
  verdicts: VerdictBuckets;
  counts: Record<VerdictBucket, number>;
}> {
  return getSubscriptionIntelVerdictsSnapshot(userId) as Promise<{
    success: boolean;
    verdicts: VerdictBuckets;
    counts: Record<VerdictBucket, number>;
  }>;
}

export async function getCategoryMigrations(userId: number): Promise<{
  success: boolean;
  migrations: CategoryMigration[];
  count: number;
}> {
  return getSubscriptionIntelMigrationsCategory(userId) as Promise<{
    success: boolean;
    migrations: CategoryMigration[];
    count: number;
  }>;
}

export async function persistMigrations(userId: number): Promise<{
  success: boolean;
  detected: number;
  upserted: number;
}> {
  return postSubscriptionIntelMigrationsPersist(userId) as Promise<{
    success: boolean;
    detected: number;
    upserted: number;
  }>;
}

export async function scheduleReminders(
  userId: number
): Promise<Record<string, unknown> & { success?: boolean }> {
  return postSubscriptionIntelRemindersScheduleUpcoming(userId) as Promise<
    Record<string, unknown> & { success?: boolean }
  >;
}

export async function getInsightsFeed(
  userId: number,
  unreadOnly = false,
  limit = 20
): Promise<{ success: boolean; insights: IntelligenceInsight[]; count: number }> {
  return getSubscriptionIntelInsightsFeed(userId, {
    unread_only: unreadOnly,
    limit,
  }) as Promise<{ success: boolean; insights: IntelligenceInsight[]; count: number }>;
}

export async function getSavings(userId: number): Promise<SavingsPayload> {
  return getSubscriptionIntelSavings(userId) as Promise<SavingsPayload>;
}

export async function markInsightRead(
  userId: number,
  insightId: number
): Promise<{ ok: boolean }> {
  return patchSubscriptionInsightRead(userId, insightId) as Promise<{ ok: boolean }>;
}
