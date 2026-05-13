/**
 * AlertDrawer — slide-out detail for review-queue alerts with Phase 7 SHAP + Phase 9 investigation.
 */

import React, { useEffect, useMemo, useRef } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { BarChart2, Sparkles, X } from "lucide-react";
import { useExplanation } from "../../hooks/risk/useExplanation";
import { ShapExplanationBars } from "../risk/ShapExplanationBars";
import { InvestigationVerdict } from "../risk/InvestigationVerdict";
import { fmtCurrency, fmtRelativeTime } from "../../utils/risk/formatters";

export function isDemoTransactionId(txnId) {
  if (txnId == null) return false;
  return /^TXN-99/i.test(String(txnId));
}

function demoExplainFromItem(item) {
  const amt = Number(item?.amount) || 0;
  const sev = String(item?.severity || "").toUpperCase();
  const baseRisk =
    sev === "CRITICAL" ? 0.86 : sev === "HIGH" ? 0.72 : sev === "MEDIUM" ? 0.55 : 0.38;
  return {
    natural_language:
      "SHAP-style breakdown (demo): ticket size and merchant novelty dominate the risk score. " +
      "Velocity and time-of-day provide secondary signals — same pattern as production explain endpoint.",
    predicted_risk_score: item?.risk_score ?? baseRisk,
    risk_action: amt > 80000 || sev === "CRITICAL" ? "challenge" : amt > 20000 ? "review" : "review",
    features: [
      { name: "amount_zscore", shap_value: 0.34, feature_value: amt },
      { name: "merchant_trust_index", shap_value: 0.21, feature_value: 0.28 },
      { name: "geo_anomaly_score", shap_value: 0.14, feature_value: 0.62 },
      { name: "hour_of_day", shap_value: 0.09, feature_value: new Date().getHours() },
      { name: "velocity_1h", shap_value: 0.08, feature_value: 2 },
      { name: "channel_upi_collect", shap_value: 0.06, feature_value: 0 },
    ],
  };
}

export function AlertDrawer({
  item,
  onClose,
  investigationState,
  onRefreshInv,
  onTriggerInv,
}) {
  const closeRef = useRef(null);
  const txnId = item?.transaction_id ?? null;
  const skipExplain = isDemoTransactionId(txnId);
  const { data: explainData, loading: explainLoading, error: explainError } = useExplanation(
    skipExplain || !txnId ? null : txnId
  );

  const demoPayload = useMemo(() => (item && skipExplain ? demoExplainFromItem(item) : null), [item, skipExplain]);

  const rawShapFeatures = useMemo(() => {
    const api = explainData?.features;
    if (Array.isArray(api) && api.length) return api;
    if (demoPayload?.features?.length) return demoPayload.features;
    return [];
  }, [explainData, demoPayload]);

  const naturalLanguage = explainData?.natural_language || demoPayload?.natural_language;
  const predictedScore = explainData?.predicted_risk_score ?? demoPayload?.predicted_risk_score;
  const riskAction = explainData?.risk_action ?? demoPayload?.risk_action;

  const shapLoading = !skipExplain && !!txnId && explainLoading;
  const shapBlocked = !skipExplain && !!txnId && explainError && !rawShapFeatures.length;

  useEffect(() => {
    if (!item) return;
    const onKey = (e) => {
      if (e.key === "Escape") onClose?.();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [item, onClose]);

  useEffect(() => {
    if (item) {
      const t = window.setTimeout(() => closeRef.current?.focus(), 80);
      return () => clearTimeout(t);
    }
    return undefined;
  }, [item]);

  const severityKey = item?.severity ? String(item.severity).toUpperCase() : "—";

  return (
    <AnimatePresence>
      {item && (
        <>
          <motion.button
            type="button"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            aria-label="Close alert details"
            className="fixed inset-0 z-[80] bg-black/60 backdrop-blur-sm"
            onClick={onClose}
          />

          <motion.aside
            role="dialog"
            aria-modal="true"
            aria-labelledby="alert-drawer-title"
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", stiffness: 380, damping: 36 }}
            className="fixed inset-y-0 right-0 z-[90] flex w-full max-w-lg flex-col border-l border-white/10 bg-[#0a0a1f]/95 shadow-[0_0_60px_-20px_rgba(124,58,237,0.45)] backdrop-blur-xl"
          >
            <header className="flex shrink-0 items-start justify-between gap-3 border-b border-white/10 p-5">
              <div className="min-w-0">
                <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-violet-300/80">Alert detail</p>
                <h2 id="alert-drawer-title" className="mt-1 font-heading text-lg font-bold tracking-tight text-white">
                  {item.merchant || item.description || `Transaction ${txnId || ""}`}
                </h2>
                <div className="mt-2 flex flex-wrap gap-2 text-xs text-exiqo-glow/65">
                  {txnId && <span className="tabular-nums">{txnId}</span>}
                  {item.amount != null && <span>{fmtCurrency(item.amount)}</span>}
                  <span>{fmtRelativeTime(item.created_at)}</span>
                  <span className="rounded-full border border-white/15 bg-white/[0.06] px-2 py-0.5 text-[10px] font-semibold uppercase text-exiqo-glow/80">
                    {severityKey}
                  </span>
                  {item.status && (
                    <span className="rounded-full border border-white/10 px-2 py-0.5 text-[10px] capitalize text-exiqo-glow/70">
                      {item.status}
                    </span>
                  )}
                </div>
              </div>
              <button
                ref={closeRef}
                type="button"
                onClick={onClose}
                className="shrink-0 rounded-xl border border-white/10 p-2 text-exiqo-glow/70 transition hover:bg-white/[0.08] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/50"
                aria-label="Close"
              >
                <X className="h-5 w-5" />
              </button>
            </header>

            <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-5 space-y-6">
              {item.notes ? (
                <div className="rounded-2xl border border-amber-500/25 bg-amber-500/10 p-4">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-amber-200/80">Reporter notes</p>
                  <p className="mt-1 text-sm leading-relaxed text-amber-50/90">&ldquo;{item.notes}&rdquo;</p>
                </div>
              ) : null}

              <section aria-labelledby="shap-heading">
                <div className="mb-3 flex items-center gap-2">
                  <BarChart2 className="h-4 w-4 text-violet-300" aria-hidden />
                  <h3 id="shap-heading" className="text-sm font-bold text-white">
                    Phase 7 — SHAP explainability
                  </h3>
                </div>
                {(predictedScore != null || riskAction) && (
                  <div className="mb-3 flex flex-wrap gap-2 text-[11px] text-exiqo-glow/70">
                    {predictedScore != null && (
                      <span className="rounded-lg border border-white/10 bg-white/[0.04] px-2 py-1 tabular-nums">
                        Model risk {typeof predictedScore === "number" ? predictedScore.toFixed(3) : predictedScore}
                      </span>
                    )}
                    {riskAction && (
                      <span className="rounded-lg border border-white/10 bg-white/[0.04] px-2 py-1 uppercase">
                        Action {riskAction}
                      </span>
                    )}
                  </div>
                )}
                {naturalLanguage && (
                  <p className="mb-3 rounded-xl border border-violet-500/20 bg-violet-500/10 p-3 text-xs leading-relaxed text-violet-100/90">
                    {naturalLanguage}
                  </p>
                )}
                {skipExplain && (
                  <p className="mb-2 text-[10px] text-exiqo-glow/45">Demo SHAP — production data loads from your explain endpoint.</p>
                )}
                {shapLoading ? (
                  <div className="space-y-2 rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                    <div className="h-3 w-[85%] max-w-full animate-pulse rounded-full bg-white/[0.08]" />
                    <div className="h-3 w-[60%] max-w-full animate-pulse rounded-full bg-white/[0.06]" />
                    <div className="h-3 w-[70%] max-w-full animate-pulse rounded-full bg-white/[0.06]" />
                  </div>
                ) : shapBlocked ? (
                  <p className="rounded-xl border border-white/10 bg-white/[0.03] p-4 text-xs text-exiqo-glow/55">
                    SHAP is not available for this transaction (needs admin scope or a scored transaction id). Phase 9
                    investigation below still works when enabled.
                  </p>
                ) : rawShapFeatures.length ? (
                  <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                    <ShapExplanationBars
                      features={rawShapFeatures}
                      loading={false}
                      error={null}
                      maxBars={8}
                      variant="dark"
                    />
                  </div>
                ) : (
                  <p className="text-xs text-exiqo-glow/50">No feature contributions to display.</p>
                )}
              </section>

              <section aria-labelledby="inv-heading">
                <div className="mb-3 flex items-center gap-2">
                  <Sparkles className="h-4 w-4 text-purple-300" aria-hidden />
                  <h3 id="inv-heading" className="text-sm font-bold text-white">
                    Phase 9 — LLM investigation
                  </h3>
                </div>
                {txnId ? (
                  <InvestigationVerdict
                    txnId={txnId}
                    state={investigationState}
                    onRefresh={onRefreshInv}
                    onTrigger={onTriggerInv}
                  />
                ) : (
                  <p className="text-xs text-exiqo-glow/50">No transaction id — investigation unavailable.</p>
                )}
              </section>
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
