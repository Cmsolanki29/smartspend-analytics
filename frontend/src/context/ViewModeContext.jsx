import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { updateDashboardMode } from "../services/api";
import { useAuth } from "./AuthContext";

const STORAGE_KEY = "smartspend_view_mode";
const VALID = new Set(["merged", "bank_only", "credit_card_only"]);

function normalizeMode(raw) {
  const s = String(raw || "merged").trim().toLowerCase();
  const map = {
    card_only: "credit_card_only",
    cards_only: "credit_card_only",
    cc_only: "credit_card_only",
    bank: "bank_only",
    merged_view: "merged",
    both: "merged",
  };
  const m = map[s] || (s.includes("card") ? "credit_card_only" : s.includes("bank") ? "bank_only" : s);
  return VALID.has(m) ? m : "merged";
}

function readStoredMode() {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    return v ? normalizeMode(v) : null;
  } catch {
    return null;
  }
}

const ViewModeContext = createContext(undefined);

export function ViewModeProvider({ children }) {
  const { user, reloadUser } = useAuth();
  const [viewMode, setViewModeState] = useState(() => {
    return readStoredMode() || normalizeMode(user?.dashboard_mode) || "merged";
  });
  const [switching, setSwitching] = useState(false);

  useEffect(() => {
    if (!user?.dashboard_mode) return;
    const fromUser = normalizeMode(user.dashboard_mode);
    setViewModeState((prev) => (prev === fromUser ? prev : fromUser));
    try {
      localStorage.setItem(STORAGE_KEY, fromUser);
    } catch {
      /* ignore */
    }
  }, [user?.dashboard_mode, user?.id]);

  const broadcastModeChange = useCallback((mode, userId) => {
    try {
      window.dispatchEvent(
        new CustomEvent("dashboardModeChanged", { detail: { mode, userId } })
      );
      window.dispatchEvent(
        new CustomEvent("smartspend:health-score-changed", { detail: { userId } })
      );
      window.dispatchEvent(
        new CustomEvent("smartspend:purchase-goals-changed", { detail: { userId } })
      );
      window.dispatchEvent(
        new CustomEvent("smartspend-financial-sync", { detail: { userId } })
      );
    } catch {
      /* ignore */
    }
  }, []);

  const switchViewMode = useCallback(
    async (newMode, { persist = true, userId, visibleSourceIds } = {}) => {
      const mode = normalizeMode(newMode);
      if (!VALID.has(mode)) return;
      const uid = Number(userId || user?.id);
      setViewModeState(mode);
      try {
        localStorage.setItem(STORAGE_KEY, mode);
      } catch {
        /* ignore */
      }
      if (!persist || !uid) {
        broadcastModeChange(mode, uid);
        return mode;
      }
      setSwitching(true);
      try {
        const resp = await updateDashboardMode({
          userId: uid,
          mode,
          visibleSourceIds: visibleSourceIds || [],
        });
        const saved = normalizeMode(resp?.mode || mode);
        setViewModeState(saved);
        try {
          localStorage.setItem(STORAGE_KEY, saved);
        } catch {
          /* ignore */
        }
        await reloadUser();
        broadcastModeChange(saved, uid);
        return saved;
      } finally {
        setSwitching(false);
      }
    },
    [user?.id, reloadUser, broadcastModeChange]
  );

  const value = useMemo(
    () => ({
      viewMode,
      setViewMode: switchViewMode,
      switchViewMode,
      switching,
    }),
    [viewMode, switchViewMode, switching]
  );

  return <ViewModeContext.Provider value={value}>{children}</ViewModeContext.Provider>;
}

export function useViewMode() {
  const ctx = useContext(ViewModeContext);
  if (!ctx) {
    throw new Error("useViewMode must be used within ViewModeProvider");
  }
  return ctx;
}

export { normalizeMode as normalizeViewMode };
