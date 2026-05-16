import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useAuth } from "./AuthContext";
import {
  getAISummary,
  getCategoryMigrations,
  getInsightsFeed,
  getSavings,
  scheduleReminders,
  markInsightRead,
  type AISummaryBundle,
  type CategoryMigration,
  type IntelligenceInsight,
  type SavingsPayload,
} from "../services/subscriptionIntelligence";
import { getSubscriptionFlowState } from "../utils/subscriptionFlowStorage";
import { syncLinkedAppsToBackend } from "../services/subscriptionDeviceSync";

export type SubscriptionIntelligenceContextValue = {
  userId: number | null;
  summary: AISummaryBundle | null;
  migrations: CategoryMigration[];
  insights: IntelligenceInsight[];
  savings: SavingsPayload | null;
  loading: boolean;
  summaryLoading: boolean;
  migrationsLoading: boolean;
  insightsLoading: boolean;
  savingsLoading: boolean;
  refreshSummary: () => Promise<void>;
  refreshMigrations: () => Promise<void>;
  refreshInsights: () => Promise<void>;
  refreshSavings: () => Promise<void>;
  refreshAll: () => Promise<void>;
  createReminders: () => Promise<void>;
  markInsightReadById: (insightId: number) => Promise<void>;
};

const SubscriptionIntelligenceContext = createContext<
  SubscriptionIntelligenceContextValue | undefined
>(undefined);

const EMPTY_VERDICTS = {
  thriving: [],
  declining: [],
  dormant: [],
  upgrade_recommended: [],
} as const;

export function SubscriptionIntelligenceProvider({
  children,
}: {
  children: ReactNode;
}) {
  const { user } = useAuth();
  const userId = user?.id ?? null;

  const [summary, setSummary] = useState<AISummaryBundle | null>(null);
  const [migrations, setMigrations] = useState<CategoryMigration[]>([]);
  const [insights, setInsights] = useState<IntelligenceInsight[]>([]);
  const [savings, setSavings] = useState<SavingsPayload | null>(null);

  const [loading, setLoading] = useState(true);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [migrationsLoading, setMigrationsLoading] = useState(false);
  const [insightsLoading, setInsightsLoading] = useState(false);
  const [savingsLoading, setSavingsLoading] = useState(false);

  const refreshSummary = useCallback(async () => {
    if (!userId) return;
    setSummaryLoading(true);
    try {
      const data = await getAISummary(userId);
      setSummary({
        verdicts: { ...EMPTY_VERDICTS, ...(data?.verdicts || {}) },
        migrations: data?.migrations ?? [],
        summary: data?.summary ?? null,
      });
    } catch (e) {
      console.error("[SubscriptionIntelligence] refreshSummary", e);
    } finally {
      setSummaryLoading(false);
    }
  }, [userId]);

  const refreshMigrations = useCallback(async () => {
    if (!userId) return;
    setMigrationsLoading(true);
    try {
      const data = await getCategoryMigrations(userId);
      setMigrations(data?.migrations || []);
    } catch (e) {
      console.error("[SubscriptionIntelligence] refreshMigrations", e);
    } finally {
      setMigrationsLoading(false);
    }
  }, [userId]);

  const refreshInsights = useCallback(async () => {
    if (!userId) return;
    setInsightsLoading(true);
    try {
      const data = await getInsightsFeed(userId, true, 40);
      setInsights(data?.insights || []);
    } catch (e) {
      console.error("[SubscriptionIntelligence] refreshInsights", e);
    } finally {
      setInsightsLoading(false);
    }
  }, [userId]);

  const refreshSavings = useCallback(async () => {
    if (!userId) return;
    setSavingsLoading(true);
    try {
      const data = await getSavings(userId);
      setSavings(data ?? null);
    } catch (e) {
      console.error("[SubscriptionIntelligence] refreshSavings", e);
    } finally {
      setSavingsLoading(false);
    }
  }, [userId]);

  const refreshAll = useCallback(async () => {
    if (!userId) {
      setSummary(null);
      setMigrations([]);
      setInsights([]);
      setSavings(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      await Promise.all([
        refreshSummary(),
        refreshMigrations(),
        refreshInsights(),
        refreshSavings(),
      ]);

      /**
       * If the hub marked apps as connected in localStorage but Postgres still has no rows
       * (failed sync, stale tab, first load after fix), push device-link once and reload intel.
       */
      const flow = getSubscriptionFlowState(userId);
      if (flow.connected && Array.isArray(flow.apps) && flow.apps.length > 0) {
        try {
          const snap = await getAISummary(userId);
          const tracked = snap?.summary?.subscriptions_tracked ?? 0;
          if (tracked === 0) {
            const res = await syncLinkedAppsToBackend(userId);
            if (res?.ok) {
              await Promise.all([
                refreshSummary(),
                refreshMigrations(),
                refreshInsights(),
                refreshSavings(),
              ]);
            }
          }
        } catch (e) {
          console.error("[SubscriptionIntelligence] auto device-link reconcile", e);
        }
      }
    } finally {
      setLoading(false);
    }
  }, [userId, refreshSummary, refreshMigrations, refreshInsights, refreshSavings]);

  const createReminders = useCallback(async () => {
    if (!userId) return;
    try {
      await scheduleReminders(userId);
      await refreshSummary();
    } catch (e) {
      console.error("[SubscriptionIntelligence] createReminders", e);
      throw e;
    }
  }, [userId, refreshSummary]);

  const markInsightReadById = useCallback(
    async (insightId: number) => {
      if (!userId) return;
      try {
        await markInsightRead(userId, insightId);
        await refreshInsights();
      } catch (e) {
        console.error("[SubscriptionIntelligence] markInsightRead", e);
        throw e;
      }
    },
    [userId, refreshInsights]
  );

  useEffect(() => {
    void refreshAll();
  }, [refreshAll]);

  useEffect(() => {
    const onRefresh = () => {
      void refreshAll();
    };
    window.addEventListener("ss-subscription-intel-refresh", onRefresh);
    return () => window.removeEventListener("ss-subscription-intel-refresh", onRefresh);
  }, [refreshAll]);

  useEffect(() => {
    const handler = () => { void refreshAll(); };
    window.addEventListener("dashboardModeChanged", handler);
    return () => window.removeEventListener("dashboardModeChanged", handler);
  }, [refreshAll]);

  const value = useMemo<SubscriptionIntelligenceContextValue>(
    () => ({
      userId,
      summary,
      migrations,
      insights,
      savings,
      loading,
      summaryLoading,
      migrationsLoading,
      insightsLoading,
      savingsLoading,
      refreshSummary,
      refreshMigrations,
      refreshInsights,
      refreshSavings,
      refreshAll,
      createReminders,
      markInsightReadById,
    }),
    [
      userId,
      summary,
      migrations,
      insights,
      savings,
      loading,
      summaryLoading,
      migrationsLoading,
      insightsLoading,
      savingsLoading,
      refreshSummary,
      refreshMigrations,
      refreshInsights,
      refreshSavings,
      refreshAll,
      createReminders,
      markInsightReadById,
    ]
  );

  return (
    <SubscriptionIntelligenceContext.Provider value={value}>
      {children}
    </SubscriptionIntelligenceContext.Provider>
  );
}

export function useSubscriptionIntelligence(): SubscriptionIntelligenceContextValue {
  const ctx = useContext(SubscriptionIntelligenceContext);
  if (!ctx) {
    throw new Error(
      "useSubscriptionIntelligence must be used within SubscriptionIntelligenceProvider"
    );
  }
  return ctx;
}
