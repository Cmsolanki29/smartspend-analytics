import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  TOKEN_REFRESH_KEY,
  authGetMe,
  authLogout,
  authRefresh,
  authSignin,
  authSignup,
  clearAuthTokens,
  getAccessToken,
  setAuthTokens,
} from "../services/api";
import { clearClientSessionState } from "../utils/sessionReset";

const SPLASH_SEEN_KEY = "smartspend_splash_seen";
/** Never block the UI longer than this on cold load (deploy + local dev). */
const AUTH_BOOT_TIMEOUT_MS = 8000;

/** Shape returned by GET /auth/me (minimal fields used in UI). */
export type AuthUser = {
  id: number;
  name?: string | null;
  email?: string | null;
  monthly_income?: number;
  onboarding_completed?: boolean;
  bank?: string | null;
  dashboard_mode?: string;
} | null;

export type SignupPayload = {
  name: string;
  email: string;
  password: string;
  signup_connection?: "link_bank" | "add_later";
  primary_bank?: string;
};

type LoadMeOptions = {
  /** When true, throw if tokens exist but /auth/me (and refresh) cannot load the user. */
  throwOnSessionError?: boolean;
};

export type AuthContextValue = {
  user: AuthUser;
  loading: boolean;
  signin: (email: string, password: string) => Promise<void>;
  signup: (payload: SignupPayload) => Promise<void>;
  logout: () => Promise<void>;
  reloadUser: (options?: LoadMeOptions) => Promise<void>;
  isAuthenticated: boolean;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser>(null);
  const [loading, setLoading] = useState(() => Boolean(getAccessToken()));

  const loadMe = useCallback(async (options?: LoadMeOptions) => {
    const token = getAccessToken();
    if (!token) {
      setUser(null);
      if (options?.throwOnSessionError) {
        throw new Error("Session was not established. Please try again.");
      }
      return;
    }
    try {
      const me = await authGetMe();
      setUser(me);
    } catch {
      const rt = localStorage.getItem(TOKEN_REFRESH_KEY);
      if (rt) {
        try {
          const data = await authRefresh(rt);
          setAuthTokens(data.access_token, data.refresh_token);
          const me = await authGetMe();
          setUser(me);
          return;
        } catch {
          /* fall through */
        }
      }
      clearAuthTokens();
      setUser(null);
      if (options?.throwOnSessionError) {
        throw new Error("Could not verify your session. Check that the API is running, then try signing in.");
      }
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!getAccessToken()) {
        setUser(null);
        setLoading(false);
        return;
      }
      setLoading(true);
      try {
        await Promise.race([
          loadMe(),
          new Promise<never>((_, reject) => {
            window.setTimeout(() => reject(new Error("auth_boot_timeout")), AUTH_BOOT_TIMEOUT_MS);
          }),
        ]);
      } catch {
        clearAuthTokens();
        setUser(null);
      }
      if (!cancelled) setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [loadMe]);

  const signin = useCallback(
    async (email: string, password: string) => {
      const data = await authSignin({ email, password });
      setAuthTokens(data.access_token, data.refresh_token);
      try {
        sessionStorage.setItem(SPLASH_SEEN_KEY, "true");
      } catch {
        /* ignore */
      }
      await loadMe({ throwOnSessionError: true });
    },
    [loadMe]
  );

  const signup = useCallback(
    async (payload: SignupPayload) => {
      const data = await authSignup(payload);
      setAuthTokens(data.access_token, data.refresh_token);
      try {
        sessionStorage.setItem(SPLASH_SEEN_KEY, "true");
        if (data?.onboarding_required !== false) {
          sessionStorage.setItem("ss_source_selection", "1");
        }
      } catch {
        /* ignore */
      }
      await loadMe({ throwOnSessionError: true });
    },
    [loadMe]
  );

  const logout = useCallback(async () => {
    const uid = user?.id;
    try {
      if (getAccessToken()) await authLogout();
    } finally {
      clearClientSessionState(uid);
      setUser(null);
    }
  }, [user?.id]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      loading,
      signin,
      signup,
      logout,
      reloadUser: loadMe,
      isAuthenticated: !!user,
    }),
    [user, loading, signin, signup, logout, loadMe]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (ctx === undefined) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

export { TOKEN_REFRESH_KEY };
