/**
 * Phase 9 LLM investigation verdict strip — shared by Alerts list and Alert drawer.
 */

import React, { useState } from "react";
import { ChevronDown, ChevronRight, Loader2, RefreshCw, Sparkles } from "lucide-react";

const VERDICT_PALETTE = {
  ALLOW: { bg: "#10b98122", border: "#10b98155", text: "#34d399" },
  FLAG: { bg: "#f59e0b22", border: "#f59e0b55", text: "#fbbf24" },
  BLOCK: { bg: "#ef444422", border: "#ef444455", text: "#f87171" },
  INVESTIGATE: { bg: "#a855f722", border: "#a855f755", text: "#c084fc" },
};

function fmtUsd4(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  return `$${n.toFixed(4)}`;
}

export function InvestigationVerdict({ txnId, state, onRefresh, onTrigger }) {
  const [expanded, setExpanded] = useState(false);
  const [running, setRunning] = useState(false);

  const runIt = async () => {
    setRunning(true);
    try {
      await onTrigger(txnId);
    } finally {
      setRunning(false);
    }
  };

  if (state === undefined) {
    return (
      <div className="mt-0 flex items-center gap-2 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2.5">
        <Loader2 size={12} className="animate-spin text-purple-300" />
        <span className="text-[11px] text-exiqo-glow/60">Loading verdict…</span>
      </div>
    );
  }

  if (state === null) {
    return (
      <div className="mt-0 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2.5">
        <span className="text-[11px] text-exiqo-glow/50 inline-flex items-center gap-1.5">
          <Sparkles size={11} className="text-purple-300" />
          No Phase 9 investigation yet
        </span>
        <button
          type="button"
          onClick={runIt}
          disabled={running}
          className="inline-flex items-center gap-1 rounded-md border border-purple-500/30 bg-purple-500/10 px-2.5 py-1 text-[11px] text-purple-200 transition hover:bg-purple-500/20 disabled:opacity-60"
        >
          {running ? <Loader2 size={11} className="animate-spin" /> : <Sparkles size={11} />}
          {running ? "Running…" : "Run Investigation →"}
        </button>
      </div>
    );
  }

  const action = String(
    state.recommended_action || state.decision || state.action || "INVESTIGATE"
  )
    .toUpperCase()
    .replace("INCONCLUSIVE", "INVESTIGATE");
  const palette = VERDICT_PALETTE[action] || VERDICT_PALETTE.INVESTIGATE;
  const reasoning =
    state.reasoning || state.agent_reasoning || state.narrative || state.summary || "";
  const cost = state.cost_usd ?? state.cost ?? null;
  const confidence = state.confidence != null ? Number(state.confidence) : null;
  const evidence = Array.isArray(state.key_evidence)
    ? state.key_evidence
    : Array.isArray(state.evidence)
      ? state.evidence
      : [];
  const recommendation =
    state.recommendation || state.recommended_action_reason || state.suggestion || "";

  return (
    <div className="mt-0 overflow-hidden rounded-lg border border-white/10 bg-white/[0.03]">
      <div className="flex flex-wrap items-center gap-2 px-3 py-2">
        <span
          className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-bold"
          style={{ background: palette.bg, borderColor: palette.border, color: palette.text }}
        >
          <Sparkles size={10} />
          {action}
        </span>
        {confidence != null && Number.isFinite(confidence) && (
          <span className="text-[11px] text-exiqo-glow/50">{(confidence * 100).toFixed(1)}% confidence</span>
        )}
        <span className="text-[11px] text-exiqo-glow/40">cost {fmtUsd4(cost)}</span>
        <div className="ml-auto flex items-center gap-1">
          <button
            type="button"
            onClick={() => onRefresh(txnId)}
            className="inline-flex items-center gap-1 rounded-md border border-white/10 px-2 py-0.5 text-[10px] text-exiqo-glow/60 transition hover:bg-white/[0.05] hover:text-exiqo-glow/90"
            title="Re-fetch verdict"
          >
            <RefreshCw size={10} />
            Refresh
          </button>
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="inline-flex items-center gap-1 rounded-md border border-white/10 px-2 py-0.5 text-[10px] text-exiqo-glow/60 transition hover:bg-white/[0.05] hover:text-exiqo-glow/90"
          >
            {expanded ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
            Details
          </button>
        </div>
      </div>

      {confidence != null && Number.isFinite(confidence) && (
        <div className="px-3 pb-2">
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/[0.06]">
            <div
              className="h-full rounded-full transition-all duration-700"
              style={{ width: `${Math.min(100, confidence * 100)}%`, background: palette.text }}
            />
          </div>
        </div>
      )}

      {expanded && (
        <div className="space-y-2 border-t border-white/[0.06] px-3 pb-3 pt-1">
          {reasoning ? (
            <div>
              <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-exiqo-glow/40">Reasoning</p>
              <p className="whitespace-pre-wrap text-[11px] leading-relaxed text-exiqo-glow/70">{reasoning}</p>
            </div>
          ) : null}
          {evidence.length > 0 && (
            <div>
              <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-exiqo-glow/40">Evidence</p>
              <ul className="space-y-0.5">
                {evidence.map((e, i) => (
                  <li key={i} className="flex gap-1.5 text-[11px] leading-snug text-exiqo-glow/60">
                    <span className="mt-0.5 shrink-0 text-purple-400">&#8226;</span>
                    {e}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {recommendation && (
            <div className="rounded-lg border border-purple-500/20 bg-purple-500/[0.06] px-2.5 py-2">
              <p className="mb-0.5 text-[10px] font-semibold uppercase tracking-wider text-purple-400/70">
                Recommendation
              </p>
              <p className="text-[11px] leading-snug text-purple-200/80">{recommendation}</p>
            </div>
          )}
          {!reasoning && evidence.length === 0 && !recommendation && (
            <p className="text-[11px] italic text-exiqo-glow/40">Agent did not return a textual narrative.</p>
          )}
        </div>
      )}
    </div>
  );
}
