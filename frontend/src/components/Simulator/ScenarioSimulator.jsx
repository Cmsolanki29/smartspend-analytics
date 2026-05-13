import React, { useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import { apiUtils, simulateScenario } from "../../services/api";
import { ErrorCard } from "../common/ErrorCard";
import { SkeletonCard } from "../common/SkeletonCard";
import { GlassCard } from "../intro/GlassCard";
import { GradientButton } from "../intro/GradientButton";

const presets = ["Food spending +30%", "Shopping +50%", "Start Rs.5000 SIP", "Salary cut 20%", "Add Rs.15000 rent"];

const ScenarioSimulator = ({ userId, month, year, presentation = "default" }) => {
  const reduce = useReducedMotion();
  const [scenario, setScenario] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const run = async () => {
    if (!scenario.trim()) return;
    setLoading(true);
    setError("");
    try {
      const data = await simulateScenario(userId, scenario, month, year);
      setResult(data);
    } catch (err) {
      setError(err.message || "Simulation failed");
    } finally {
      setLoading(false);
    }
  };

  const verdictClass = String(result?.verdict || "").toLowerCase();
  const compact = presentation === "compact";

  const inner = (
    <>
      <div className={`flex flex-wrap gap-2 ${compact ? "mb-3" : "preset-wrap mb-3"}`}>
        {presets.map((label) => (
          <button
            key={label}
            type="button"
            className="chip-btn min-h-[48px] rounded-full border border-white/10 bg-white/[0.04] px-3 py-2 text-xs font-medium text-exiqo-glow/90 transition hover:bg-white/[0.08] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60 md:min-h-0"
            onClick={() => setScenario(label)}
          >
            {label}
          </button>
        ))}
      </div>

      <div className={`flex flex-col gap-2 ${compact ? "sm:flex-row sm:items-stretch" : "sim-input-row"}`}>
        <label htmlFor="scenario-sim-input" className="sr-only">
          Describe a spending scenario
        </label>
        <input
          id="scenario-sim-input"
          value={scenario}
          onChange={(e) => setScenario(e.target.value)}
          placeholder="What if I spend ₹X on Y?"
          className="min-h-[48px] flex-1 rounded-xl border border-white/10 bg-white/[0.04] px-4 py-3 text-sm text-white placeholder:text-exiqo-glow/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60"
        />
        <GradientButton type="button" size="md" onClick={run} disabled={loading || !scenario.trim()} leadingIcon={<ArrowRight className="h-4 w-4" aria-hidden />}>
          Run
        </GradientButton>
      </div>

      {loading ? (
        <div className="mt-3">
          <p className="mb-2 text-xs text-exiqo-glow/60">Running scenario against your profile…</p>
          <SkeletonCard lines={4} height={140} />
        </div>
      ) : null}
      {error ? (
        <div className="mt-3">
          <ErrorCard message={error} onRetry={() => scenario.trim() && run()} />
        </div>
      ) : null}

      {result && !loading ? (
        <motion.article
          initial={reduce ? false : { opacity: 0, y: 12, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ type: "spring", stiffness: 420, damping: 28 }}
          className="simulation-result mt-4 rounded-xl border border-white/[0.08] bg-white/[0.04] p-4 space-y-3"
        >
          <div>
            <h4 className="text-xs font-bold uppercase tracking-wide text-exiqo-glow/60">Scenario</h4>
            <p className="mt-1 text-sm font-semibold text-white">{result.scenario_title || scenario}</p>
          </div>

          {/* Core metrics */}
          <div className="grid gap-2 text-sm text-exiqo-glow/85 sm:grid-cols-2">
            <p className="tabular-nums">
              <span className="text-exiqo-glow/55">Savings </span>
              <span className="text-white">{apiUtils.formatINR(result.current_state?.monthly_savings || 0)}</span>
              <span className="mx-1 text-exiqo-glow/40">→</span>
              <span className={result.projected_state?.monthly_savings < result.current_state?.monthly_savings ? "text-red-300" : "text-emerald-300"}>
                {apiUtils.formatINR(result.projected_state?.monthly_savings || 0)}
              </span>
            </p>
            <p className="tabular-nums">
              <span className="text-exiqo-glow/55">Health </span>
              <span className="text-white">{result.current_state?.health_score || 0}/100</span>
              <span className="mx-1 text-exiqo-glow/40">→</span>
              <span className={result.projected_state?.health_score < result.current_state?.health_score ? "text-red-300" : "text-emerald-300"}>
                {result.projected_state?.health_score || 0}/100
              </span>
            </p>
            <p className="tabular-nums">
              <span className="text-exiqo-glow/55">Savings rate </span>
              <span className="text-white">{(result.current_state?.savings_rate || 0).toFixed(1)}%</span>
              <span className="mx-1 text-exiqo-glow/40">→</span>
              <span className={result.projected_state?.savings_rate < result.current_state?.savings_rate ? "text-red-300" : "text-emerald-300"}>
                {(result.projected_state?.savings_rate || 0).toFixed(1)}%
              </span>
            </p>
            <p className="tabular-nums">
              <span className="text-exiqo-glow/55">Annual impact </span>
              <span className={result.impact?.annual_impact < 0 ? "text-red-300 font-semibold" : "text-emerald-300 font-semibold"}>
                {result.impact?.annual_impact < 0 ? "−" : "+"}{apiUtils.formatINR(Math.abs(result.impact?.annual_impact || 0))}
              </span>
            </p>
          </div>

          {/* Real commitments context */}
          {(result.impact?.emi_burden > 0 || result.impact?.active_goals > 0 || result.impact?.upcoming_festivals > 0) && (
            <div className="rounded-lg border border-amber-400/20 bg-amber-400/5 px-3 py-2 text-xs text-amber-200/80 flex flex-wrap gap-3">
              {result.impact?.emi_burden > 0 && (
                <span>EMI load: <strong className="text-amber-200">{apiUtils.formatINR(result.impact.emi_burden)}/mo</strong></span>
              )}
              {result.impact?.active_goals > 0 && (
                <span>Active goals: <strong className="text-amber-200">{result.impact.active_goals}</strong></span>
              )}
              {result.impact?.upcoming_festivals > 0 && (
                <span>Upcoming festivals: <strong className="text-amber-200">{result.impact.upcoming_festivals}</strong></span>
              )}
            </div>
          )}

          <div className={`verdict-pill ${verdictClass}`}>Verdict: {result.verdict}</div>
          <p className="text-sm leading-relaxed text-white/85">{result.advice}</p>
          {(result.alternatives || []).length > 0 && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-exiqo-glow/55 mb-1">Smarter alternatives</p>
              <ul className="list-disc space-y-1 pl-5 text-sm text-exiqo-glow/80">
                {result.alternatives.map((item, i) => (
                  <li key={i}>{item}</li>
                ))}
              </ul>
            </div>
          )}
          {result.computed_from === "real_transactions" && (
            <p className="text-[10px] text-exiqo-glow/35 text-right">Computed from your real transaction history</p>
          )}
        </motion.article>
      ) : null}
    </>
  );

  if (compact) {
    return (
      <GlassCard padding="sm" surface="panel" className="border-white/[0.08] lg:pb-24">
        <h3 className="font-heading text-sm font-semibold text-white">What-if simulator</h3>
        <p className="mt-1 text-xs text-exiqo-glow/65">Model a purchase or lifestyle change.</p>
        <div className="mt-3">{inner}</div>
      </GlassCard>
    );
  }

  return (
    <section className="glass-card border-white/[0.08]">
      <div className="panel-head">
        <h3>Scenario Simulator</h3>
      </div>
      {inner}
    </section>
  );
};

export default ScenarioSimulator;
