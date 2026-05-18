import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { getFinancialSummary } from "../services/api";
import { useAuth } from "./AuthContext";
import { useViewMode } from "./ViewModeContext";

const DEFAULT_SUMMARY = {
  monthly_income: 0,
  monthly_emi_total: 0,
  active_emis: [],
  festival_reserved: 0,
  projected_monthly_emi: 0,
  available_for_purchase: 0,
};

const FinancialContext = createContext(undefined);

export function FinancialProvider({ children }) {
  const { user } = useAuth();
  const { viewMode } = useViewMode();
  const userId = Number(user?.id) || 0;
  const [financialSummary, setFinancialSummary] = useState(DEFAULT_SUMMARY);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const refreshFinancials = useCallback(async () => {
    if (!userId) {
      setFinancialSummary(DEFAULT_SUMMARY);
      return DEFAULT_SUMMARY;
    }
    setLoading(true);
    setError("");
    try {
      const data = await getFinancialSummary(userId, viewMode);
      const next = {
        monthly_income: data?.monthly_income ?? 0,
        monthly_emi_total: data?.monthly_emi_total ?? 0,
        active_emis: Array.isArray(data?.active_emis) ? data.active_emis : [],
        festival_reserved: data?.festival_reserved ?? 0,
        projected_monthly_emi: data?.projected_monthly_emi ?? 0,
        available_for_purchase: data?.available_for_purchase ?? 0,
      };
      setFinancialSummary(next);
      return next;
    } catch (e) {
      setError(e?.message || "Could not load financial summary");
      setFinancialSummary(DEFAULT_SUMMARY);
      return DEFAULT_SUMMARY;
    } finally {
      setLoading(false);
    }
  }, [userId, viewMode]);

  useEffect(() => {
    refreshFinancials();
  }, [refreshFinancials]);

  useEffect(() => {
    const handler = () => refreshFinancials();
    window.addEventListener("dashboardModeChanged", handler);
    window.addEventListener("smartspend-financial-sync", handler);
    window.addEventListener("smartspend:purchase-goals-changed", handler);
    window.addEventListener("smartspend:festival-plans-changed", handler);
    return () => {
      window.removeEventListener("dashboardModeChanged", handler);
      window.removeEventListener("smartspend-financial-sync", handler);
      window.removeEventListener("smartspend:purchase-goals-changed", handler);
      window.removeEventListener("smartspend:festival-plans-changed", handler);
    };
  }, [refreshFinancials]);

  const value = useMemo(
    () => ({
      financialSummary,
      refreshFinancials,
      loading,
      error,
    }),
    [financialSummary, refreshFinancials, loading, error]
  );

  return <FinancialContext.Provider value={value}>{children}</FinancialContext.Provider>;
}

export function useFinancial() {
  const ctx = useContext(FinancialContext);
  if (!ctx) {
    throw new Error("useFinancial must be used within FinancialProvider");
  }
  return ctx;
}
