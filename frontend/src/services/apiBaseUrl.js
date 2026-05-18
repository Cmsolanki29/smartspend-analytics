/**
 * Single source of truth for the API base path.
 *
 * Development: same-origin `/api` → setupProxy.js → backend (8002 default, auto-fallback 8001).
 * Production: set REACT_APP_API_URL at build time to your deployed API, e.g.
 *   https://api.yourdomain.com/api
 */
const DEV_PORTS = [8002, 8001];

export function getApiBaseUrl() {
  if (process.env.NODE_ENV === "development") {
    return "/api";
  }
  const u = (process.env.REACT_APP_API_URL || "").trim();
  if (u) return u.endsWith("/api") ? u : `${u.replace(/\/$/, "")}/api`;
  // Same-origin when UI and API are served behind one host (nginx, Cloud Run, etc.)
  return "/api";
}

/** Root URL for /health (no /api prefix). */
export function getBackendRootUrl() {
  if (process.env.NODE_ENV === "development") {
    return "";
  }
  const base = getApiBaseUrl().replace(/\/api\/?$/, "");
  return base || "";
}

export function getDevBackendHint() {
  return `Run .\\start-dev.ps1 (recommended) or .\\start-backend.ps1 — API on port ${DEV_PORTS[0]} (fallback ${DEV_PORTS[1]})`;
}

export function getDevHealthUrl(port = DEV_PORTS[0]) {
  return `http://127.0.0.1:${port}/health`;
}
