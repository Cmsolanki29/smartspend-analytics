/**
 * CRA dev-server proxy — forwards /api and /health to a live backend.
 * Re-resolves target every few seconds so a hung :8002 does not block login after restart.
 */
const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");
const { createProxyMiddleware } = require("http-proxy-middleware");

const PORTS_TRY_ORDER = [8002, 8001];
const PORT_FILE = path.join(__dirname, "..", ".backend-port");
const RESOLVE_EVERY_MS = 8000;

function readPortFile() {
  try {
    const n = parseInt(String(fs.readFileSync(PORT_FILE, "utf8")).trim(), 10);
    return Number.isFinite(n) && n > 0 ? n : null;
  } catch {
    return null;
  }
}

function fetchHealthJson(port) {
  const timeoutSec = 2;
  if (process.platform === "win32") {
    try {
      const r = spawnSync(
        "powershell",
        [
          "-NoProfile",
          "-Command",
          `(Invoke-WebRequest -Uri http://127.0.0.1:${port}/health -TimeoutSec ${timeoutSec} -UseBasicParsing).Content`,
        ],
        { encoding: "utf8", timeout: 4500, windowsHide: true }
      );
      if (r.status !== 0) return null;
      return JSON.parse(String(r.stdout || "").trim());
    } catch {
      return null;
    }
  }
  try {
    const r = spawnSync(
      "curl",
      ["-s", "--max-time", String(timeoutSec), `http://127.0.0.1:${port}/health`],
      { encoding: "utf8", timeout: 4500 }
    );
    if (r.status !== 0) return null;
    return JSON.parse(String(r.stdout || "").trim());
  } catch {
    return null;
  }
}

function hasPlannerCapabilities(health) {
  if (!health || health.status !== "healthy") return false;
  const caps = health.api_capabilities;
  if (!caps) return false;
  return caps.purchase_goal_complete === true && caps.festival_custom_event === true;
}

function isHealthy(health) {
  return health && (health.status === "healthy" || health.status === "ok");
}

function resolveBackendTarget() {
  if (process.env.REACT_APP_PROXY_TARGET) {
    return process.env.REACT_APP_PROXY_TARGET.replace(/\/$/, "");
  }

  const fromFile = readPortFile();
  const ports = [];
  if (fromFile) ports.push(fromFile);
  for (const p of PORTS_TRY_ORDER) {
    if (!ports.includes(p)) ports.push(p);
  }

  let anyHealthy = null;

  for (const port of ports) {
    const health = fetchHealthJson(port);
    if (hasPlannerCapabilities(health)) {
      const target = `http://127.0.0.1:${port}`;
      console.log(`[setupProxy] Planner API at ${target}`);
      return target;
    }
    if (isHealthy(health) && !anyHealthy) {
      anyHealthy = port;
    }
  }

  if (anyHealthy) {
    const target = `http://127.0.0.1:${anyHealthy}`;
    console.warn(
      `[setupProxy] Using ${target} (healthy). For Purchase/Festival APIs run .\\start-backend.ps1 on port 8002.`,
    );
    return target;
  }

  const fallback = "http://127.0.0.1:8002";
  console.warn(`[setupProxy] No healthy backend — defaulting to ${fallback}. Run .\\start-dev.ps1`);
  return fallback;
}

let activeTarget = resolveBackendTarget();
let lastResolvedAt = Date.now();

function getActiveTarget() {
  if (Date.now() - lastResolvedAt > RESOLVE_EVERY_MS) {
    activeTarget = resolveBackendTarget();
    lastResolvedAt = Date.now();
  }
  return activeTarget;
}

function forceReResolve() {
  lastResolvedAt = 0;
  return getActiveTarget();
}

function makeProxy() {
  return createProxyMiddleware({
    router: () => getActiveTarget(),
    changeOrigin: true,
    onError: (err, req, res) => {
      console.warn("[setupProxy] proxy error, re-resolving backend:", err?.message || err);
      forceReResolve();
      if (res && !res.headersSent) {
        res.writeHead(502, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ detail: "Backend unreachable. Run .\\start-dev.ps1 then refresh." }));
      }
    },
  });
}

module.exports = function setupProxy(app) {
  console.log(`[setupProxy] Initial target: ${activeTarget}`);
  app.use("/api", makeProxy());
  app.use("/health", makeProxy());
  app.use("/docs", makeProxy());
  app.use("/openapi.json", makeProxy());
};
