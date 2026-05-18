import axios from "axios";
import { getApiBaseUrl, getBackendRootUrl, getDevBackendHint, getDevHealthUrl } from "./apiBaseUrl";

/** Long-running AI insight bundle (parallel Groq/OpenAI calls). */
export const INSIGHTS_FETCH_MS = 42000;
/** Dashboard charts + scoped SQL — must exceed cold-start / merged-scope queries. */
export const DASHBOARD_FETCH_MS = 45000;

/** Dev: `/api` → setupProxy.js → backend port 8002. Prod: `REACT_APP_API_URL` or 8002 default. */
const BASE_URL = getApiBaseUrl();

export const TOKEN_ACCESS_KEY = "smartspend_access_token";
export const TOKEN_REFRESH_KEY = "smartspend_refresh_token";

export function getAccessToken() {
  try {
    return localStorage.getItem(TOKEN_ACCESS_KEY);
  } catch {
    return null;
  }
}

export function setAuthTokens(access, refresh) {
  try {
    localStorage.setItem(TOKEN_ACCESS_KEY, access);
    localStorage.setItem(TOKEN_REFRESH_KEY, refresh);
  } catch {
    /* ignore */
  }
}

export function clearAuthTokens() {
  try {
    localStorage.removeItem(TOKEN_ACCESS_KEY);
    localStorage.removeItem(TOKEN_REFRESH_KEY);
  } catch {
    /* ignore */
  }
}

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 20000,
  headers: {
    "Content-Type": "application/json",
  },
});

const refreshClient = axios.create({
  baseURL: BASE_URL,
  timeout: 15000,
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use((config) => {
  const path = String(config.url || "");
  const publicAuth = path.includes("/auth/signin") || path.includes("/auth/signup");
  if (!publicAuth) {
    const t = getAccessToken();
    if (t) {
      config.headers = config.headers || {};
      config.headers.Authorization = `Bearer ${t}`;
    }
  } else if (config.headers) {
    delete config.headers.Authorization;
  }
  return config;
});

api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const orig = error.config;
    if (!orig || orig._retry || !error.response || error.response.status !== 401) {
      return Promise.reject(error);
    }
    const url = String(orig.url || "");
    if (url.includes("/auth/signin") || url.includes("/auth/signup") || url.includes("/auth/refresh")) {
      return Promise.reject(error);
    }
    let rt;
    try {
      rt = localStorage.getItem(TOKEN_REFRESH_KEY);
    } catch {
      rt = null;
    }
    if (!rt) {
      clearAuthTokens();
      return Promise.reject(error);
    }
    try {
      orig._retry = true;
      const { data } = await refreshClient.post("/auth/refresh", { refresh_token: rt });
      setAuthTokens(data.access_token, data.refresh_token);
      orig.headers = orig.headers || {};
      orig.headers.Authorization = `Bearer ${data.access_token}`;
      return api(orig);
    } catch (e) {
      clearAuthTokens();
      return Promise.reject(e);
    }
  }
);

const authDetail = (error) => {
  const d = error.response?.data?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) {
    return d
      .map((x) => {
        if (x && typeof x === "object" && "msg" in x) {
          const loc = Array.isArray(x.loc) ? x.loc.filter(Boolean).join(".") : "";
          return loc ? `${loc}: ${x.msg}` : x.msg;
        }
        return typeof x === "string" ? x : JSON.stringify(x);
      })
      .join("; ");
  }
  if (d && typeof d === "object") return JSON.stringify(d);
  // Axios: no response = browser could not connect (backend down, wrong host/port, or CORS blocked).
  if (!error.response) {
    const msg = String(error.message || "");
    const code = error.code || "";
    if (code === "ECONNABORTED" || /timeout/i.test(msg)) {
      return (
        `Request timed out before the API responded (${BASE_URL}). ` +
        `If the backend just started, wait ~30s (DB + ML warmup) and try again. ` +
        `${getDevBackendHint()}. Check ${getDevHealthUrl()} in your browser.`
      );
    }
    if (msg === "Network Error" || code === "ERR_NETWORK") {
      return (
        `Cannot reach the API (${BASE_URL}). ` +
        `${getDevBackendHint()}. ` +
        `Open ${getDevHealthUrl()} or ${getDevHealthUrl(8001)} — one should return {"status":"healthy"}. ` +
        `Restart the frontend after starting the backend so the dev proxy picks the correct port.`
      );
    }
  }
  return error.message || "Request failed";
};

const AUTH_TIMEOUT_MS = 60000;

/** Dev: GET /health via proxy, then direct :8002 / :8001. Prod: GET {API_ROOT}/health */
export async function pingBackendHealth(timeoutMs = 5000) {
  const urls = [];
  const root = getBackendRootUrl();
  if (root) {
    urls.push(`${root.replace(/\/$/, "")}/health`);
  } else {
    urls.push("/health", "http://127.0.0.1:8002/health", "http://127.0.0.1:8001/health");
  }
  const perTry = Math.max(1500, Math.min(3000, Math.floor(timeoutMs / urls.length)));
  for (const url of urls) {
    try {
      const { status, data } = await axios.get(url, { timeout: perTry });
      if (status === 200 && data && (data.status === "healthy" || data.status === "ok")) {
        return true;
      }
    } catch {
      /* try next endpoint */
    }
  }
  return false;
}

export async function authSignin(body) {
  try {
    const { data } = await api.post("/auth/signin", body, { timeout: AUTH_TIMEOUT_MS });
    return data;
  } catch (e) {
    throw new Error(authDetail(e));
  }
}

export async function authSignup(body) {
  try {
    const { data } = await api.post("/auth/signup", body, { timeout: AUTH_TIMEOUT_MS });
    return data;
  } catch (e) {
    throw new Error(authDetail(e));
  }
}

export async function authGetMe() {
  try {
    const { data } = await api.get("/auth/me", { timeout: 10000 });
    return data;
  } catch (e) {
    throw new Error(authDetail(e));
  }
}

/** Positive integer for API paths / bodies (avoids NaN → JSON null → 422). */
function apiUserId(userId) {
  const n = typeof userId === "number" && Number.isFinite(userId) ? userId : Number(userId);
  if (!Number.isFinite(n) || n < 1 || !Number.isInteger(n)) {
    throw new Error("Select a valid user profile (user id missing). Refresh the page.");
  }
  return n;
}

function apiSourceId(sourceId) {
  const n = typeof sourceId === "number" && Number.isFinite(sourceId) ? sourceId : Number(sourceId);
  if (!Number.isFinite(n) || n < 1 || !Number.isInteger(n)) {
    throw new Error("Invalid account id. Reload Connected accounts and try again.");
  }
  return n;
}

/** Attach dashboard scope to query params when provided. */
function withScope(params, scope) {
  const p = { ...(params || {}) };
  if (scope) p.scope = scope;
  return p;
}

/** Connected financial sources + dashboard scope */
export async function getConnectedSources(userId) {
  try {
    const { data } = await api.get("/sources/connected", {
      params: { user_id: apiUserId(userId) },
      timeout: 20000,
    });
    return data;
  } catch (e) {
    throw new Error(authDetail(e));
  }
}

export async function updateDashboardMode({ userId, mode, visibleSourceIds }) {
  try {
    const uid = apiUserId(userId);
    const ids = (visibleSourceIds || [])
      .map((id) => Number(id))
      .filter((n) => Number.isFinite(n) && Number.isInteger(n) && n > 0);
    const payload = {
      user_id: uid,
      mode,
      visible_source_ids: ids,
    };
    // JSON body only (duplicate query+body confused some proxies); allow slow DB during dev ML warmup.
    const { data } = await api.post("/user/update-dashboard-mode", payload, { timeout: 60000 });
    return data;
  } catch (e) {
    throw new Error(authDetail(e));
  }
}

export async function deleteConnectedSource({ userId, sourceId }) {
  try {
    const uid = apiUserId(userId);
    const sid = apiSourceId(sourceId);
    const { data } = await api.delete(`/sources/${sid}`, {
      params: { user_id: uid },
      timeout: 30000,
    });
    return data;
  } catch (e) {
    throw new Error(authDetail(e));
  }
}

export async function toggleSourceVisibility({ userId, sourceId, visible }) {
  try {
    const uid = apiUserId(userId);
    const sid = apiSourceId(sourceId);
    const vis = Boolean(visible);
    const payload = { user_id: uid, source_id: sid, visible: vis };
    const { data } = await api.post("/sources/toggle-visibility", payload, { timeout: 60000 });
    return data;
  } catch (e) {
    throw new Error(authDetail(e));
  }
}

/** Mock Account Aggregator — public bank list */
export async function onboardingGetBanks() {
  try {
    const { data } = await api.get("/onboarding/available-banks", { timeout: 60000 });
    return data;
  } catch (e) {
    throw new Error(authDetail(e));
  }
}

export async function onboardingGetStatus() {
  try {
    const { data } = await api.get("/onboarding/status", { timeout: 60000 });
    return data;
  } catch (e) {
    throw new Error(authDetail(e));
  }
}

/** `bank_slug`: hdfc | sbi | icici | axis | kotak */
export async function onboardingLinkBank(body) {
  try {
    const { data } = await api.post("/onboarding/link-bank", body, { timeout: 60000 });
    return data;
  } catch (e) {
    throw new Error(authDetail(e));
  }
}

export async function otpSend(body) {
  try {
    const { data } = await api.post("/otp/send", body, { timeout: 30000 });
    return data;
  } catch (e) {
    throw new Error(authDetail(e));
  }
}

export async function otpVerify(body) {
  try {
    const { data } = await api.post("/otp/verify", body, { timeout: 30000 });
    return data;
  } catch (e) {
    throw new Error(authDetail(e));
  }
}

export async function authLogout() {
  try {
    const { data } = await api.post("/auth/logout");
    return data;
  } catch (e) {
    throw new Error(authDetail(e));
  }
}

export async function authRefresh(refreshToken) {
  const { data } = await refreshClient.post("/auth/refresh", { refresh_token: refreshToken });
  return data;
}

const handle = (response) => response.data;
const throwFriendly = (error) => {
  if (error.response?.data?.detail) {
    const d = error.response.data.detail;
    if (typeof d === "string") {
      throw new Error(d);
    }
    if (d && typeof d === "object") {
      if (typeof d.message === "string") {
        throw new Error(d.message);
      }
      if (d.error === "insights_unavailable") {
        throw new Error(
          typeof d.message === "string"
            ? d.message
            : "AI insights are temporarily unavailable. Please try again in a moment."
        );
      }
      throw new Error(JSON.stringify(d));
    }
  }
  throw new Error(error.message || "Request failed");
};

const request = async (promise) => {
  try {
    const response = await promise;
    return handle(response);
  } catch (error) {
    throwFriendly(error);
  }
};

/** Retry transient failures (cold start, reload) — safe for any user_id. */
export async function requestWithRetry(makePromise, { retries = 3, delayMs = 1200 } = {}) {
  let lastErr;
  for (let attempt = 0; attempt < retries; attempt += 1) {
    try {
      return await request(makePromise(attempt));
    } catch (e) {
      lastErr = e;
      const msg = String(e?.message || "").toLowerCase();
      const retryable =
        msg.includes("timeout") ||
        msg.includes("network error") ||
        msg.includes("not found") ||
        msg.includes("502") ||
        msg.includes("503") ||
        msg.includes("504") ||
        msg.includes("starting up");
      if (!retryable || attempt >= retries - 1) throw e;
      await new Promise((r) => setTimeout(r, delayMs * (attempt + 1)));
    }
  }
  throw lastErr;
}

export async function waitForBackendReady(maxWaitMs = 45000) {
  const started = Date.now();
  while (Date.now() - started < maxWaitMs) {
    try {
      const ok = await pingBackendHealth(4000);
      if (ok) return true;
    } catch {
      /* retry */
    }
    await new Promise((r) => setTimeout(r, 1500));
  }
  return false;
}

export const getUsers = async () => request(api.get("/users"));
export const getUser = async (userId) => request(api.get(`/users/${userId}`));

/**
 * One-shot dashboard aggregate. Backend returns the user row, current-month
 * income/expense/saved, recent anomalies, spending-by-category, 12-month trends,
 * health score, unread-alert count, fraud_pending_count, last_synced (max
 * across linked banks), and last_login.
 */
export const getDashboardSummary = async (userId) =>
  request(api.get(`/dashboard/${userId}`));

export const getTransactions = async (userId, params = {}, scope = null) =>
  request(api.get(`/transactions/${userId}`, { params: withScope(params, scope) }));

export const getTransactionSummary = async (userId, monthOrOpts, yearMaybe, scopeMaybe) => {
  const params = {};
  let scope = scopeMaybe;
  if (monthOrOpts != null && typeof monthOrOpts === "object" && !Array.isArray(monthOrOpts)) {
    const o = monthOrOpts;
    if (o.month != null) params.month = o.month;
    if (o.year != null) params.year = o.year;
    if (o.scope) scope = o.scope;
  } else {
    if (monthOrOpts != null) params.month = monthOrOpts;
    if (yearMaybe != null) params.year = yearMaybe;
  }
  return request(api.get(`/transactions/${userId}/summary`, { params: withScope(params, scope) }));
};

export const getSpendingAnalysis = async (userId, month, year, scope = null) =>
  requestWithRetry(
    () =>
      api.get(`/analysis/${userId}/spending`, {
        params: withScope({ month, year }, scope),
        timeout: DASHBOARD_FETCH_MS,
      }),
    { retries: 2, delayMs: 1000 }
  );

export const getMonthlyTrends = async (userId, scope = null) =>
  requestWithRetry(
    () =>
      api.get(`/analysis/${userId}/trends`, {
        params: withScope({}, scope),
        timeout: DASHBOARD_FETCH_MS,
      }),
    { retries: 2, delayMs: 1000 }
  );

export const getTopMerchants = async (userId, month, year, scope = null) =>
  requestWithRetry(
    () =>
      api.get(`/analysis/${userId}/merchants`, {
        params: withScope({ month, year }, scope),
        timeout: DASHBOARD_FETCH_MS,
      }),
    { retries: 2, delayMs: 1000 }
  );

export const getAnomalies = async (userId, severity = null, scope = null) =>
  requestWithRetry(
    () =>
      api.get(`/anomalies/${userId}`, {
        params: withScope(severity ? { severity } : {}, scope),
        timeout: DASHBOARD_FETCH_MS,
      }),
    { retries: 2, delayMs: 1000 }
  );

export const getAnomalyStats = async (userId, scope = null) =>
  requestWithRetry(
    () =>
      api.get(`/anomalies/${userId}/stats`, {
        params: withScope({}, scope),
        timeout: DASHBOARD_FETCH_MS,
      }),
    { retries: 2, delayMs: 1000 }
  );

export const runMLDetection = async (userId) =>
  request(api.post(`/anomalies/${userId}/run-detection`));

export const getHealthScore = async (userId, month, year, scope = null) => {
  const params = { month, year };
  if (scope) params.scope = scope;
  return requestWithRetry(
    () => api.get(`/health-score/${userId}`, { params, timeout: DASHBOARD_FETCH_MS }),
    { retries: 2, delayMs: 1000 }
  );
};

export const getHealthHistory = async (userId) =>
  request(api.get(`/health-score/${userId}/history`));

export const getInsights = async (userId, month, year) =>
  request(
    api.get(`/insights/${userId}`, { params: { month, year }, timeout: INSIGHTS_FETCH_MS })
  );

/**
 * Streams GET /insights/{userId}/insights-stream (SSE). Invokes onEvent for each parsed JSON object.
 * Resolves with final payload `{ user, period, insights, recommendations, generated_at }` or rejects.
 */
export const invalidateInsightsCache = async (userId, { month, year, scope } = {}) => {
  const params = new URLSearchParams();
  if (month != null) params.set("month", String(month));
  if (year != null) params.set("year", String(year));
  if (scope) params.set("scope", scope);
  const qs = params.toString();
  return request(
    api.post(`/insights/${userId}/invalidate-cache${qs ? `?${qs}` : ""}`, {}, { timeout: 15000 })
  );
};

export async function fetchInsightsSse(userId, month, year, onEvent, options = {}) {
  const { scope = null, signal: externalSignal = null, refresh = false } = options;
  const base = getApiBaseUrl();
  const params = new URLSearchParams();
  if (month != null) params.set("month", String(month));
  if (year != null) params.set("year", String(year));
  if (scope) params.set("scope", scope);
  if (refresh) params.set("refresh", "true");
  const qs = params.toString();
  const url = `${base}/insights/${userId}/insights-stream${qs ? `?${qs}` : ""}`;
  const token = getAccessToken();
  const ctrl = new AbortController();
  if (externalSignal) {
    if (externalSignal.aborted) ctrl.abort();
    else externalSignal.addEventListener("abort", () => ctrl.abort(), { once: true });
  }
  const tid = window.setTimeout(() => ctrl.abort(), INSIGHTS_FETCH_MS);
  try {
    const res = await fetch(url, {
      method: "GET",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      signal: ctrl.signal,
    });
    if (!res.ok) {
      throw new Error("Insights are taking longer than usual.");
    }
    const reader = res.body?.getReader();
    if (!reader) throw new Error("Unable to read insight stream.");
    const dec = new TextDecoder();
    let buf = "";
    let finalPayload = null;
    outer: while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let sep;
      while ((sep = buf.indexOf("\n\n")) >= 0) {
        const block = buf.slice(0, sep).trim();
        buf = buf.slice(sep + 2);
        if (!block.startsWith("data:")) continue;
        const raw = block.replace(/^data:\s*/, "");
        let evt;
        try {
          evt = JSON.parse(raw);
        } catch {
          continue;
        }
        if (typeof onEvent === "function") onEvent(evt);
        if (evt.error) {
          throw new Error(evt.message || "AI insights are temporarily unavailable.");
        }
        if (evt.done && evt.data) {
          finalPayload = evt.data;
          try {
            await reader.cancel();
          } catch {
            /* ignore */
          }
          break outer;
        }
      }
    }
    if (!finalPayload) {
      throw new Error("AI insights are temporarily unavailable. Please try again in a moment.");
    }
    return finalPayload;
  } catch (e) {
    const aborted = e?.name === "AbortError" || /aborted/i.test(String(e?.message || ""));
    if (aborted) {
      throw new Error("Insights are taking longer than usual.");
    }
    throw e;
  } finally {
    window.clearTimeout(tid);
  }
}

export const getQuickSummary = async (userId, opts = {}) => {
  const params = {};
  if (opts.month != null) params.month = opts.month;
  if (opts.year != null) params.year = opts.year;
  return requestWithRetry(
    () =>
      api.get(`/insights/${userId}/quick-summary`, {
        params: withScope(params, opts.scope),
        timeout: DASHBOARD_FETCH_MS,
      }),
    { retries: 2, delayMs: 1000 }
  );
};

export const getFinancialSummary = async (userId, scope = null) =>
  request(api.get(`/financial-summary/${apiUserId(userId)}`, { params: withScope({}, scope) }));

export const getAnomalyExplanation = async (userId, transactionId) =>
  request(api.get(`/insights/${userId}/anomaly/${transactionId}`));

export const simulateScenario = async (userId, scenario, month, year) =>
  request(api.post(`/insights/${userId}/simulate`, { scenario, month, year }));

export const getHealthNarrative = async (userId, month, year) =>
  request(api.get(`/insights/${userId}/health-narrative`, { params: { month, year } }));

export const getEmiReport = async (userId, scope = null) => {
  const uid = apiUserId(userId);
  return requestWithRetry(
    () =>
      api.get(`/emi/${uid}`, {
        params: withScope({}, scope),
        timeout: 45000,
      }),
    { retries: 3, delayMs: 1500 },
  );
};

export const scanEmi = async (userId) => request(api.post(`/emi/${userId}/scan`));

/** Standard loan EMI + amortization (reducing-balance formula). */
export const postLoanCalculate = async (userId, payload) =>
  request(api.post(`/emi/${userId}/loan-calculate`, payload));

export const calculateEmiImpact = async (userId, newEmiMonthly) =>
  request(api.post(`/emi/${userId}/calculate-impact`, { new_emi_monthly: newEmiMonthly }));

/** EMI + purchase goals + fixed costs vs income; includes postpone_options for Purchase Planner. */
export const calculateEmiAffordability = async (userId, newEmiMonthly) =>
  request(api.post(`/emi/${userId}/affordability`, { new_emi_monthly: newEmiMonthly }));

/** Postpone goal to a specific date — with festival label fallback. */
export const postponePurchaseGoal = async (userId, goalId, body) => {
  try {
    return await request(api.post(`/purchases/${userId}/goals/${goalId}/postpone`, body));
  } catch {
    return await request(api.post(`/emi/${userId}/purchase/${goalId}/postpone-date`, body));
  }
};

/** CA-style deterministic check — tries the dedicated route, falls back to inline route. */
export const postEmiAffordabilityCheck = async (userId, proposedNewEmi) => {
  try {
    return await request(api.post(`/emi/${userId}/affordability-check`, { proposed_new_emi: proposedNewEmi }));
  } catch {
    // Inline fallback route (always registered inside emi_detector router)
    return await request(api.post(`/emi/${userId}/affordability-check`, { proposed_new_emi: proposedNewEmi }));
  }
};

/** Postpone by date — tries purchase route, falls back to inline emi_detector route. */
export const postPurchasePostponeGoal = async (userId, goalId, postponeMonths) => {
  try {
    return await request(api.post(`/purchases/${userId}/${goalId}/postpone`, { postpone_months: postponeMonths }));
  } catch {
    return await request(api.post(`/emi/${userId}/purchase/${goalId}/postpone-months`, { postpone_months: postponeMonths }));
  }
};

/** Postpone goal to specific date (with festival label). */
export const postponePurchaseGoalToDate = async (userId, goalId, body) => {
  try {
    return await request(api.post(`/purchases/${userId}/goals/${goalId}/postpone`, body));
  } catch {
    return await request(api.post(`/emi/${userId}/purchase/${goalId}/postpone-date`, body));
  }
};

export const getSubscriptions = async (userId) =>
  request(api.get(`/subscriptions/${userId}`));

/** Subscription Intelligence hub (device usage, verdicts, substitutions, reminders). */
export const getSubscriptionIntelligenceHub = async (userId) =>
  request(api.get(`/subscription-intelligence/${userId}/hub`));

export const postSubscriptionDeviceLink = async (userId, body) =>
  request(api.post(`/subscription-intelligence/${userId}/device-link`, body));

export const postSubscriptionEvaluate = async (userId, subscriptionId) =>
  request(api.post(`/subscription-intelligence/${userId}/subscriptions/${subscriptionId}/evaluate`, {}));

export const getSubscriptionRecommendation = async (userId, subscriptionId) =>
  request(api.get(`/subscription-intelligence/${userId}/subscriptions/${subscriptionId}/recommendation`));

export const getSubscriptionRemindersPending = async (userId, params = {}) =>
  request(api.get(`/subscription-intelligence/${userId}/reminders/pending`, { params }));

/** payload: { action } or { action, accountability_reason } — reason required for remind_later only when subscription escalation tier >= 2 */
export const postSubscriptionReminderAction = async (userId, reminderId, payload) => {
  const body = typeof payload === "string" ? { action: payload } : payload;
  const uid = Number(userId);
  const rid = Number(reminderId);
  return request(api.post(`/subscription-intelligence/${uid}/reminders/${rid}/action`, body));
};

export const patchSubscriptionInsightRead = async (userId, insightId) =>
  request(api.patch(`/subscription-intelligence/${userId}/insights/${insightId}/read`, {}));

/** Phase 3 subscription-intelligence bundle (verdicts + migrations + rollups). */
export const getSubscriptionIntelHealth = () =>
  request(api.get("/subscription-intelligence/health"));

export const getSubscriptionIntelAiSummary = (userId) =>
  request(api.get(`/subscription-intelligence/${userId}/ai-summary`));

export const getSubscriptionIntelVerdictsSnapshot = (userId) =>
  request(api.get(`/subscription-intelligence/${userId}/verdicts/snapshot`));

export const getSubscriptionIntelMigrationsCategory = (userId) =>
  request(api.get(`/subscription-intelligence/${userId}/migrations/category`));

export const postSubscriptionIntelMigrationsPersist = (userId) =>
  request(api.post(`/subscription-intelligence/${userId}/migrations/category/persist`));

export const postSubscriptionIntelRemindersScheduleUpcoming = (userId) =>
  request(api.post(`/subscription-intelligence/${userId}/reminders/schedule-upcoming`));

export const getSubscriptionIntelInsightsFeed = (userId, params = {}) =>
  request(api.get(`/subscription-intelligence/${userId}/insights/feed`, { params }));

export const getSubscriptionIntelSavings = (userId) =>
  request(api.get(`/subscription-intelligence/${userId}/savings`));

export const postSubscriptionSimulateNextDay = async (userId) =>
  request(api.post(`/subscription-intelligence/${userId}/reminders/simulate-next-day`, {}));

export const postSubscriptionResetDemo = async (userId) =>
  request(api.post(`/subscription-intelligence/${userId}/reset-demo`, {}));

export const getDarkPatterns = async (userId, scope = null) =>
  request(api.get(`/dark-patterns/${userId}`, { params: withScope({}, scope) }));

export const getRupeeTraps = async (userId, scope = null) =>
  request(api.get(`/dark-patterns/${userId}/rupee-traps`, { params: withScope({}, scope) }));

export const scanDarkPatterns = async (userId) =>
  request(api.post(`/dark-patterns/${userId}/scan`));

export const resolveDarkPattern = async (userId, patternId) =>
  request(api.post(`/dark-patterns/${userId}/${patternId}/resolve`));

/** Proactive pattern alerts (upcoming renewals / trial ends). */
export const getPatternAlertsActive = async (userId) =>
  request(api.get(`/pattern-alerts/${userId}/active`, { timeout: 12000 }));

export const generatePatternAlerts = async (userId) =>
  request(api.post(`/pattern-alerts/${userId}/generate`, {}, { timeout: 20000 }));

export const snoozePatternAlert = async (userId, payload) =>
  request(api.post(`/pattern-alerts/${userId}/snooze`, payload));

export const dismissPatternAlert = async (userId, payload) =>
  request(api.post(`/pattern-alerts/${userId}/dismiss`, payload));

export const actionPatternAlert = async (userId, payload) =>
  request(api.post(`/pattern-alerts/${userId}/action`, payload));

export const getPatternAlertSavings = async (userId) =>
  request(api.get(`/pattern-alerts/${userId}/savings`, { timeout: 10000 }));

export const downloadPatternAlertCalendarBlob = async (userId, alertId) => {
  const res = await api.get(`/pattern-alerts/${userId}/calendar/${alertId}`, {
    responseType: "blob",
    timeout: 15000,
  });
  return res.data;
};

export const getFraudShieldGlobalSummary = async () => request(api.get("/fraud-shield/summary"));

export const getFraudShieldPatterns = async () => request(api.get("/fraud-shield/patterns"));

export const getFraudShieldAnalyze = async (userId, scope = null) =>
  request(api.get(`/fraud-shield/${userId}/analyze`, { params: withScope({}, scope) }));

export const postFraudShieldCheckTransaction = async (userId, payload) =>
  request(api.post(`/fraud-shield/${userId}/check-transaction`, payload));

export const getFraudShieldPhasesStatus = async (userId) =>
  request(api.get(`/fraud-shield/${userId}/phases-status`));

export const getFraudShieldAlerts = async (userId, scope = null) =>
  request(api.get(`/fraud-shield/${userId}/alerts`, { params: withScope({}, scope) }));

/** Scoped fraud alerts (alias — same data, JWT-protected). */
export const getUserFraudAlerts = async (userId, scope = null) =>
  request(api.get(`/${apiUserId(userId)}/fraud-alerts`, { params: withScope({}, scope) }));

export const getUserBehaviour = async (userId, scope = null) =>
  request(api.get(`/${apiUserId(userId)}/behaviour`, { params: withScope({}, scope) }));

export const getUserInvestigations = async (userId, scope = null) =>
  request(api.get(`/${apiUserId(userId)}/investigation`, { params: withScope({}, scope) }));

export const getLinkedAccounts = async (userId) =>
  request(api.get(`/${apiUserId(userId)}/linked-accounts`));

export const postFraudShieldAlertAction = async (userId, alertId, action) =>
  request(api.post(`/fraud-shield/${userId}/alerts/${alertId}/action`, { action }));

/** Record alert action when the row is keyed by transaction (merged txn alerts). */
export const postFraudShieldAlertActionByTransaction = async (userId, transactionId, action) =>
  request(api.post(`/fraud-shield/${userId}/alerts/by-transaction/${transactionId}/action`, { action }));

export const getFraudShieldStats = async (userId, scope = null) =>
  request(api.get(`/fraud-shield/${userId}/stats`, { params: withScope({}, scope) }));

export const getFestivals = async (userId) => request(api.get(`/festivals/${userId}`));

export const getFestivalHistory = async (userId) =>
  request(api.get(`/festivals/${userId}/history`));

export const postFestivalSetBudget = async (userId, payload) =>
  request(api.post(`/festivals/${userId}/set-budget`, payload));

export const putFestivalUpdateSavings = async (userId, payload) => {
  const uid = apiUserId(userId);
  try {
    return await request(api.put(`/festivals/${uid}/planner/savings`, payload));
  } catch (e) {
    if (String(e.message || "").toLowerCase().includes("not found")) {
      return request(api.put(`/festivals/${uid}/update-savings`, payload));
    }
    throw e;
  }
};

const isHttpNotFound = (e) => {
  const m = String(e.message || "").toLowerCase();
  return m.includes("not found") || m.includes("status code 404");
};

const STALE_BACKEND_HINT =
  "Backend API is outdated or on the wrong port. Stop all Python/uvicorn windows, then run .\\start-dev.ps1 (uses port 8002). Restart the frontend after it compiles.";

export const postFestivalAddEvent = async (userId, payload) => {
  const uid = apiUserId(userId);
  const is404 = isHttpNotFound;
  const body = {
    festival_name: payload.festival_name,
    festival_date: payload.festival_date,
    planned_budget: Number(payload.planned_budget) || 0,
    category_budgets: payload.category_budgets || {},
  };
  const tryRoutes = [
    () => api.post(`/festivals/${uid}/events`, body),
    () => api.post(`/festivals/${uid}/planner/event`, body),
  ];
  let lastErr;
  for (const call of tryRoutes) {
    try {
      return await request(call());
    } catch (e) {
      lastErr = e;
      if (!is404(e)) throw e;
    }
  }
  const amount = body.planned_budget;
  try {
    await request(
      api.post(`/festivals/${uid}/set-budget`, {
        festival_name: payload.festival_name,
        planned_budget: amount > 0 ? amount : Math.max(amount, 5000),
        festival_date: payload.festival_date,
        category_budgets: body.category_budgets,
      }),
    );
    const listed = await getFestivals(uid);
    const match = (listed?.upcoming_festivals || []).find(
      (f) =>
        String(f.festival_name || "").toLowerCase() ===
          String(payload.festival_name || "").toLowerCase() &&
        String(f.festival_date || "").slice(0, 10) === String(payload.festival_date || "").slice(0, 10),
    );
    if (match) return { success: true, event: match };
  } catch {
    /* fall through */
  }
  if (lastErr && !is404(lastErr)) throw lastErr;
  throw new Error(STALE_BACKEND_HINT);
};

export const getFestivalEventDetails = async (userId, festivalName, festivalDate, refresh = true) => {
  const uid = apiUserId(userId);
  const name = encodeURIComponent(festivalName);
  try {
    return await request(
      api.get(`/festivals/${uid}/planner/event-details/${name}`, {
        params: { festival_date: festivalDate, refresh },
      }),
    );
  } catch (e) {
    if (String(e.message || "").toLowerCase().includes("not found")) {
      return request(
        api.get(`/festivals/${uid}/events/${name}/details`, {
          params: { festival_date: festivalDate, refresh },
        }),
      );
    }
    throw e;
  }
};

export const getFestivalImportantDays = async (userId) =>
  request(api.get(`/festivals/${userId}/important-days`));

export const postFestivalImportantDay = async (userId, payload) =>
  request(api.post(`/festivals/${userId}/important-days`, payload));

export const putFestivalImportantDay = async (userId, eventId, payload) =>
  request(api.put(`/festivals/${userId}/important-days/${eventId}`, payload));

export const deleteFestivalImportantDay = async (userId, eventId) =>
  request(api.delete(`/festivals/${userId}/important-days/${eventId}`));

export const putFestivalImportantDayReminder = async (userId, eventId, payload) => {
  const uid = apiUserId(userId);
  const eid = Number(eventId);
  try {
    return await request(api.put(`/festivals/${uid}/planner/reminder/${eid}`, payload));
  } catch (e) {
    if (isHttpNotFound(e)) {
      return request(api.put(`/festivals/${uid}/important-days/${eid}/reminder`, payload));
    }
    throw e;
  }
};

export const getPurchases = async (userId) => request(api.get(`/purchases/${userId}`));

export const postPurchaseAddGoal = async (userId, payload) =>
  request(api.post(`/purchases/${userId}/add-goal`, payload));

export const putPurchaseUpdateSavings = async (userId, goalId, amountSaved) =>
  request(api.put(`/purchases/${userId}/${goalId}/update-savings`, { amount_saved: amountSaved }));

export const deletePurchaseGoal = async (userId, goalId) =>
  request(api.delete(`/purchases/${userId}/${goalId}`));

export const completePurchaseGoal = async (userId, goalId) => {
  const uid = apiUserId(userId);
  const gid =
    typeof goalId === "number" && Number.isFinite(goalId)
      ? goalId
      : Number(goalId);
  if (!Number.isFinite(gid) || gid < 1 || !Number.isInteger(gid)) {
    throw new Error("Invalid goal id. Refresh the page and try again.");
  }
  try {
    return await request(api.post(`/purchases/${uid}/${gid}/complete`));
  } catch (e) {
    const msg = String(e?.message || "");
    if (!/not found/i.test(msg)) throw e;
    try {
      return await request(api.post(`/purchases/${uid}/goals/${gid}/complete`));
    } catch (e2) {
      if (/not found/i.test(String(e2?.message || ""))) {
        throw new Error(STALE_BACKEND_HINT);
      }
      throw e2;
    }
  }
};

/** Postpone purchase goal by months (Purchase Planner or EMI). */
export const postPurchasePostponeMonths = async (userId, goalId, postponeMonths) =>
  postPurchasePostponeGoal(userId, goalId, postponeMonths);

// ── Financial Engine (Interconnected System) ─────────────────────────────────

/** Full monthly surplus breakdown from the financial engine. Short timeout — non-critical. */
export const getFinancialState = async (userId) =>
  request(api.get(`/financial-state/${userId}`, { timeout: 8000 }));

export const forceRecalculate = async (userId) =>
  request(api.post(`/financial-state/${userId}/recalculate`, {}, { timeout: 10000 }));

/** Notifications — short timeout, non-critical */
// opts: { limit?, unreadOnly? } — passing a bare number is treated as { limit: n } for older call sites.
export const getNotifications = async (userId, opts = {}) => {
  const limit = typeof opts === "number" ? opts : opts.limit ?? 20;
  const unreadOnly = typeof opts === "number" ? false : Boolean(opts.unreadOnly);
  return request(
    api.get(`/notifications/${userId}`, {
      params: { limit, unread_only: unreadOnly },
      timeout: 6000,
    })
  );
};

export const markNotificationsRead = async (userId, body) =>
  request(api.post(`/notifications/${userId}/mark-read`, body, { timeout: 5000 }));

/** Impact log */
export const getImpactLog = async (userId, limit = 20) =>
  request(api.get(`/impact-log/${userId}`, { params: { limit }, timeout: 8000 }));

/** Family events / trips */
export const getFamilyEvents = async (userId) =>
  request(api.get(`/family-events/${userId}`));

export const postFamilyEvent = async (userId, body) =>
  request(api.post(`/family-events/${userId}`, body));

export const postponeFamilyEvent = async (userId, eventId, body) =>
  request(api.patch(`/family-events/${userId}/${eventId}/postpone`, body));

export const completeFamilyEvent = async (userId, eventId) =>
  request(api.patch(`/family-events/${userId}/${eventId}/complete`));

export const deleteFamilyEvent = async (userId, eventId) =>
  request(api.delete(`/family-events/${userId}/${eventId}`));

export const apiUtils = {
  formatINR: (amount) =>
    new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: "INR",
      maximumFractionDigits: 0,
    }).format(Number(amount || 0)),
};
