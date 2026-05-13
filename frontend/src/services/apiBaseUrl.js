/**
 * Single source of truth for the API base path.
 *
 * In **development**, CRA proxies same-origin `/api` → `package.json` "proxy"
 * (default `http://127.0.0.1:8001`). That avoids (1) CORS drift when the UI runs
 * on 3000/3011/etc. and (2) broken sign-in when `REACT_APP_API_URL` was pointed at
 * a stale port (e.g. 8012) while the backend is on 8001.
 *
 * In **production**, set `REACT_APP_API_URL` at build time if the API is not co-hosted.
 */
export function getApiBaseUrl() {
  if (process.env.NODE_ENV === "development") {
    return "/api";
  }
  const u = (process.env.REACT_APP_API_URL || "").trim();
  return u || "http://localhost:8001/api";
}
