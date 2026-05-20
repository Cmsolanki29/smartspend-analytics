import React, { useState, useEffect, useRef, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useToast } from "../common/Toast";
import { getApiBaseUrl } from "../../services/apiBaseUrl";

const ADMIN_TOKEN = process.env.REACT_APP_ADMIN_TOKEN || "dev-admin-secret";

function getCardStyle(score) {
  if (score > 0.8) return "border-red-500 bg-red-500/5 shadow-red-500/10 shadow-lg animate-pulse";
  if (score > 0.6) return "border-orange-500 bg-orange-500/5";
  if (score > 0.3) return "border-yellow-500 bg-yellow-500/5";
  return "border-green-500/50 bg-gray-800/50";
}

function getScoreColor(score) {
  if (score > 0.8) return "text-red-400";
  if (score > 0.6) return "text-orange-400";
  if (score > 0.3) return "text-yellow-400";
  return "text-green-400";
}

function getBadgeStyle(score) {
  if (score > 0.8) return "bg-red-500/20 text-red-300";
  if (score > 0.6) return "bg-orange-500/20 text-orange-300";
  if (score > 0.3) return "bg-yellow-500/20 text-yellow-300";
  return "bg-green-500/20 text-green-300";
}

function getRiskLabel(score) {
  if (score > 0.8) return "CRITICAL";
  if (score > 0.6) return "HIGH";
  if (score > 0.3) return "MEDIUM";
  return "LOW";
}

export default function RealTimeFraudFeed({ userId = 1 }) {
  const { showToast } = useToast();
  const [isRunning, setIsRunning] = useState(false);
  const [events, setEvents] = useState([]);
  const [stats, setStats] = useState({ total: 0, flagged: 0, safe: 0 });
  const [investigating, setInvestigating] = useState(null);
  const [investigationResult, setInvestigationResult] = useState(null);
  const [investigationLoading, setInvestigationLoading] = useState(false);
  const [investigationSteps, setInvestigationSteps] = useState([]);
  const pollingRef = useRef(null);
  const prevEventsLengthRef = useRef(0);
  const apiBase = getApiBaseUrl();

  const handleStart = useCallback(async () => {
    try {
      const res = await fetch(`${apiBase}/simulator/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ interval_seconds: 5, user_id: userId }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail || "Failed to start simulator", "error");
        return;
      }
      setIsRunning(true);
      if (pollingRef.current) clearInterval(pollingRef.current);
      pollingRef.current = setInterval(async () => {
        try {
          const pollRes = await fetch(`${apiBase}/simulator/recent`);
          if (!pollRes.ok) return;
          const data = await pollRes.json();
          if (data.events && data.events.length > prevEventsLengthRef.current) {
            const newEvents = data.events.slice(prevEventsLengthRef.current);
            setEvents((prev) => [...newEvents.reverse(), ...prev].slice(0, 50));
            prevEventsLengthRef.current = data.events.length;
            newEvents.forEach((evt) => {
              if (evt.risk_score > 0.7) {
                showToast(
                  `Suspicious: ₹${Number(evt.amount).toLocaleString("en-IN")} to ${evt.merchant} — Risk: ${(evt.risk_score * 100).toFixed(0)}%`,
                  "warning",
                );
              }
            });
          }
          if (data.stats) setStats(data.stats);
          if (typeof data.running === "boolean" && !data.running) {
            setIsRunning(false);
          }
        } catch {
          /* keep polling */
        }
      }, 2000);
    } catch {
      showToast("Could not start live demo", "error");
    }
  }, [apiBase, showToast, userId]);

  const handleStop = useCallback(async () => {
    try {
      await fetch(`${apiBase}/simulator/stop`, { method: "POST" });
    } catch {
      /* ignore */
    }
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
    setIsRunning(false);
  }, [apiBase]);

  const handleReset = useCallback(async () => {
    try {
      await fetch(`${apiBase}/simulator/reset`, { method: "POST" });
    } catch {
      showToast("Reset request failed", "error");
      return;
    }
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
    setIsRunning(false);
    setEvents([]);
    setStats({ total: 0, flagged: 0, safe: 0 });
    setInvestigating(null);
    setInvestigationResult(null);
    setInvestigationSteps([]);
    prevEventsLengthRef.current = 0;
    showToast("Demo data cleared — app restored to original state", "success");
  }, [apiBase, showToast]);

  const handleInvestigate = useCallback(
    async (event) => {
      setInvestigating(event);
      setInvestigationLoading(true);
      setInvestigationResult(null);
      setInvestigationSteps([]);

      const steps = [
        "Checking transaction history...",
        "Analyzing merchant reputation...",
        "Checking time pattern...",
        "Evaluating geo-velocity...",
      ];
      steps.forEach((step, i) => {
        setTimeout(() => setInvestigationSteps((prev) => [...prev, step]), i * 800);
      });

      try {
        const url = `${apiBase}/risk/investigations/${event.transaction_id}/run?user_id=${userId}&triggered_by=simulator_demo`;
        const res = await fetch(url, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Admin-Token": ADMIN_TOKEN,
          },
        });
        const data = await res.json().catch(() => ({}));
        if (res.ok && !data.skipped) {
          const verdict = String(data.decision || data.recommended_action || "REVIEW").toUpperCase();
          setInvestigationResult({
            verdict: verdict === "BLOCK" || verdict === "DENY" ? "BLOCK" : verdict === "ALLOW" ? "ALLOW" : "REVIEW",
            confidence:
              data.confidence != null
                ? `${Math.round(Number(data.confidence) * (Number(data.confidence) <= 1 ? 100 : 1))}%`
                : null,
            narrative: data.narrative || data.summary || "",
            fallback: false,
          });
        } else {
          throw new Error(data.reason || data.detail || "Investigation unavailable");
        }
      } catch {
        setInvestigationResult({
          verdict: event.risk_score > 0.8 ? "BLOCK" : "REVIEW",
          confidence: `${(event.risk_score * 100).toFixed(0)}%`,
          narrative:
            "AI Investigation unavailable. ML analysis: " + (event.risk_factors || []).join(", "),
          fallback: true,
        });
      } finally {
        setInvestigationLoading(false);
      }
    },
    [apiBase, userId],
  );

  useEffect(() => {
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, []);

  useEffect(() => {
    fetch(`${apiBase}/simulator/status`)
      .then((r) => r.json())
      .then((data) => {
        if (data.running) {
          setIsRunning(true);
          if (data.stats) setStats(data.stats);
        }
      })
      .catch(() => {});
  }, [apiBase]);

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="space-y-4">
      <motion.div className="flex items-center justify-between" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
        <motion.div className="flex items-center gap-2">
          <span
            className={`h-3 w-3 rounded-full ${isRunning ? "bg-green-500 animate-pulse" : "bg-red-500"}`}
          />
          <h2 className="text-lg font-semibold text-white">
            {isRunning ? "LIVE" : "STOPPED"} — Real-Time Fraud Detection
          </h2>
        </motion.div>
      </motion.div>

      <motion.div className="flex flex-wrap gap-3">
        <button
          type="button"
          onClick={handleStart}
          disabled={isRunning}
          className="px-4 py-2 rounded-lg bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white text-sm font-medium"
        >
          Start Live Demo
        </button>
        <button
          type="button"
          onClick={handleStop}
          disabled={!isRunning}
          className="px-4 py-2 rounded-lg bg-gray-600 hover:bg-gray-700 disabled:opacity-50 text-white text-sm font-medium"
        >
          Stop
        </button>
        <button
          type="button"
          onClick={handleReset}
          className="px-4 py-2 rounded-lg bg-red-600/20 hover:bg-red-600/30 text-red-400 text-sm font-medium border border-red-500/30"
        >
          Reset Demo Data
        </button>
      </motion.div>

      <div className="flex gap-6 text-sm text-gray-400">
        <span>
          Scored: <span className="text-white font-medium">{stats.total}</span>
        </span>
        <span>
          Flagged: <span className="text-red-400 font-medium">{stats.flagged}</span>
        </span>
        <span>
          Safe: <span className="text-green-400 font-medium">{stats.safe}</span>
        </span>
      </div>

      <div className="space-y-2 max-h-[500px] overflow-y-auto pr-1">
        <AnimatePresence>
          {events.length === 0 && !isRunning && (
            <motion.div className="text-center py-12 text-gray-500">
              Click &quot;Start Live Demo&quot; to begin real-time fraud detection
            </motion.div>
          )}
          {events.map((evt) => (
            <motion.div
              key={evt.id}
              initial={{ opacity: 0, y: -20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.3 }}
              className={`p-4 rounded-lg border-l-4 ${getCardStyle(evt.risk_score)}`}
            >
              <motion.div className="flex justify-between items-start gap-4">
                <div className="min-w-0 flex-1">
                  <span className="text-white font-medium">{evt.merchant}</span>
                  <span className="text-white font-bold ml-2">
                    ₹{Number(evt.amount).toLocaleString("en-IN")}
                  </span>
                  <motion.div className="text-xs text-gray-400 mt-1">
                    {evt.payment_method} · {evt.category} · {new Date(evt.timestamp).toLocaleTimeString()}
                  </motion.div>
                  {evt.risk_score > 0.6 && evt.risk_factors && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {evt.risk_factors.map((f, i) => (
                        <span
                          key={i}
                          className="px-2 py-0.5 rounded-full bg-red-500/20 text-red-300 text-xs"
                        >
                          {f}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                <div className="text-right shrink-0">
                  <span className={`text-sm font-bold ${getScoreColor(evt.risk_score)}`}>
                    {(evt.risk_score * 100).toFixed(0)}%
                  </span>
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full mt-1 inline-block ${getBadgeStyle(evt.risk_score)}`}
                  >
                    {getRiskLabel(evt.risk_score)}
                  </span>
                </div>
              </motion.div>
              {evt.risk_score > 0.8 && (
                <button
                  type="button"
                  onClick={() => handleInvestigate(evt)}
                  disabled={investigationLoading && investigating?.id === evt.id}
                  className="mt-3 px-3 py-1.5 rounded-md bg-purple-600/30 hover:bg-purple-600/50 text-purple-300 text-xs font-medium border border-purple-500/30 disabled:opacity-50"
                >
                  Investigate with AI
                </button>
              )}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      {investigating && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="p-4 rounded-lg bg-gray-800/80 border border-purple-500/30"
        >
          <h3 className="text-purple-300 font-medium mb-3">
            AI Investigation: {investigating.merchant} ₹
            {Number(investigating.amount).toLocaleString("en-IN")}
          </h3>
          <div className="space-y-2">
            {investigationSteps.map((step, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                className="text-sm text-gray-300"
              >
                {step}
              </motion.div>
            ))}
            {investigationLoading && investigationSteps.length >= 4 && (
              <p className="text-xs text-gray-500 animate-pulse">Running Phase 9 agent…</p>
            )}
          </div>
          {investigationResult && !investigationLoading && (
            <div className="mt-4 p-3 rounded-lg bg-gray-900/50 border border-gray-700">
              <motion.div
                className={`text-lg font-bold ${
                  investigationResult.verdict === "BLOCK" ? "text-red-400" : "text-yellow-400"
                }`}
              >
                VERDICT: {investigationResult.verdict}
                {investigationResult.fallback ? " (fallback)" : ""}
              </motion.div>
              {investigationResult.confidence && (
                <div className="text-sm text-gray-400">Confidence: {investigationResult.confidence}</div>
              )}
              {investigationResult.narrative && (
                <p className="text-sm text-gray-300 mt-2">{investigationResult.narrative}</p>
              )}
            </div>
          )}
        </motion.div>
      )}
    </motion.div>
  );
}
