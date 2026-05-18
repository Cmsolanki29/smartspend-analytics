/**
 * Global app data context — userId, viewMode, linked accounts, refetchAll.
 * Mount once inside Auth + ViewMode providers.
 */
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { getAccessToken } from "../services/api";
import { getApiBaseUrl } from "../services/apiBaseUrl";
import { useToast } from "../components/common/Toast";
import { dispatchDataUpdated, refetchAll } from "../utils/refetchAll";
import { useAuth } from "./AuthContext";
import { useViewMode } from "./ViewModeContext";

const AppDataContext = createContext(undefined);

export function AppDataProvider({ children }) {
  const { user } = useAuth();
  const { viewMode } = useViewMode();
  const { showToast } = useToast();
  const userId = Number(user?.id) || 0;
  const [linkedAccounts, setLinkedAccounts] = useState([]);
  const [linkedLoading, setLinkedLoading] = useState(false);

  const userProfile = useMemo(
    () => ({
      id: userId,
      firstName: (user?.name || "").trim().split(/\s+/)[0] || "",
      fullName: user?.name || "",
      email: user?.email || "",
    }),
    [userId, user?.name, user?.email]
  );

  const refreshLinkedAccounts = useCallback(async () => {
    if (!userId) {
      setLinkedAccounts([]);
      return [];
    }
    setLinkedLoading(true);
    try {
      const token = getAccessToken();
      const base = getApiBaseUrl();
      const res = await fetch(`${base}/${userId}/linked-accounts`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) {
        setLinkedAccounts([]);
        return [];
      }
      const data = await res.json();
      const list = data?.linked_accounts || data?.sources || [];
      setLinkedAccounts(Array.isArray(list) ? list : []);
      return list;
    } catch {
      setLinkedAccounts([]);
      return [];
    } finally {
      setLinkedLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    refreshLinkedAccounts();
  }, [refreshLinkedAccounts]);

  const clearContext = useCallback(() => {
    setLinkedAccounts([]);
  }, []);

  const globalRefetchAll = useCallback(
    (detail) => {
      refetchAll({ userId, ...detail });
      refreshLinkedAccounts();
    },
    [userId, refreshLinkedAccounts]
  );

  useEffect(() => {
    if (!userId) return undefined;
    const base = getApiBaseUrl().replace(/\/api\/?$/, "");
    const token = getAccessToken();
    const qs = new URLSearchParams({ user_id: String(userId) });
    if (token) qs.set("token", token);
    const wsUrl = `${base.replace(/^http/, "ws")}/ws?${qs.toString()}`;
    let ws;
    let cancelled = false;
    try {
      ws = new WebSocket(wsUrl);
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          if (msg?.event === "data_updated" && Number(msg.user_id) === userId) {
            const name = msg.source_name || "Statement";
            showToast(`${name} data is ready!`, "success");
            globalRefetchAll({ sourceName: name });
          }
        } catch {
          /* ignore */
        }
      };
      ws.onerror = () => {
        /* fallback: DOM events from upload still work */
      };
    } catch {
      /* ignore ws setup errors */
    }
    const onDom = (ev) => {
      const uid = Number(ev?.detail?.user_id);
      if (uid && uid !== userId) return;
      const name = ev?.detail?.source_name || "Statement";
      if (ev?.detail?.source_name) showToast(`${name} data is ready!`, "success");
      globalRefetchAll(ev?.detail);
    };
    window.addEventListener("smartspend:data-updated", onDom);
    return () => {
      cancelled = true;
      window.removeEventListener("smartspend:data-updated", onDom);
      if (ws && !cancelled) {
        try {
          ws.close();
        } catch {
          /* ignore */
        }
      }
    };
  }, [userId, globalRefetchAll, showToast]);

  useEffect(() => {
    const onCleared = () => clearContext();
    window.addEventListener("smartspend:session-cleared", onCleared);
    return () => window.removeEventListener("smartspend:session-cleared", onCleared);
  }, [clearContext]);

  const value = useMemo(
    () => ({
      userId,
      viewMode,
      linkedAccounts,
      linkedLoading,
      userProfile,
      refreshLinkedAccounts,
      refetchAll: globalRefetchAll,
      clearContext,
      dispatchDataUpdated: (detail) => dispatchDataUpdated({ userId, ...detail }),
    }),
    [
      userId,
      viewMode,
      linkedAccounts,
      linkedLoading,
      userProfile,
      refreshLinkedAccounts,
      globalRefetchAll,
      clearContext,
    ]
  );

  return <AppDataContext.Provider value={value}>{children}</AppDataContext.Provider>;
}

export function useAppData() {
  const ctx = useContext(AppDataContext);
  if (!ctx) throw new Error("useAppData must be used within AppDataProvider");
  return ctx;
}

export default AppDataContext;
