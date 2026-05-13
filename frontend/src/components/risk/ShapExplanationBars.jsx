/**
 * ShapExplanationBars — horizontal bar chart for SHAP feature contributions.
 * Phase 7 explainability. Gracefully handles loading / error / missing data.
 *
 * Props:
 *   features  [{name, shap_value, feature_value, normalizedValue, width, positive}]
 *   loading   {bool}
 *   error     {Error|null}
 *   maxBars   {number} default 5
 *   variant   {"light"|"dark"} — dark for glass panels (e.g. FraudShield drawer)
 */

import React from "react";
import { motion } from "framer-motion";
import { topFeatures, humanizeFeatureName } from "../../utils/risk/shapHelpers";
import { RiskStatePlaceholder } from "./RiskStatePlaceholder";

function Bar({ feature, index, dark }) {
  const color = feature.positive ? "#ef4444" : "#10b981";
  const label = humanizeFeatureName(feature.name);
  const valLabel =
    feature.feature_value != null ? String(feature.feature_value).slice(0, 8) : "";

  const nameCls = dark
    ? "w-32 shrink-0 truncate text-right text-exiqo-glow/75"
    : "w-32 shrink-0 truncate text-gray-600 text-right";
  const trackCls = dark ? "relative flex-1 h-4 overflow-hidden rounded-sm bg-white/[0.08]" : "relative flex-1 h-4 rounded-sm overflow-hidden bg-gray-100";
  const valCls = dark ? "w-14 shrink-0 text-right text-exiqo-glow/55" : "w-14 shrink-0 text-gray-400 text-right";
  const shapCls = dark ? "w-14 shrink-0 text-right font-mono font-medium" : "w-14 shrink-0 font-mono font-medium text-right";

  return (
    <motion.div
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.06 }}
      className="flex items-center gap-2 text-xs"
    >
      <span className={nameCls} title={label}>
        {label}
      </span>

      <div className={trackCls}>
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${feature.width}%` }}
          transition={{ duration: 0.5, delay: index * 0.06, ease: "easeOut" }}
          className="absolute inset-y-0 left-0 rounded-sm"
          style={{ backgroundColor: color, opacity: 0.8 }}
        />
      </div>

      <span className={valCls}>{valLabel}</span>

      <span className={shapCls} style={{ color }}>
        {feature.positive ? "+" : ""}
        {feature.shap_value?.toFixed(3) ?? "—"}
      </span>
    </motion.div>
  );
}

export function ShapExplanationBars({
  features = [],
  loading = false,
  error = null,
  maxBars = 5,
  variant = "light",
}) {
  const dark = variant === "dark";

  if (loading || error || !features.length) {
    if (dark) {
      if (loading) {
        return (
          <div className="space-y-2 py-2">
            <div className="h-3 w-[80%] animate-pulse rounded-full bg-white/[0.08]" />
            <div className="h-3 w-[55%] animate-pulse rounded-full bg-white/[0.06]" />
          </div>
        );
      }
      if (error) {
        return (
          <p className="rounded-lg border border-white/10 bg-white/[0.04] p-3 text-xs text-amber-200/80">
            {error?.message?.includes("Network") ? "Offline — could not load SHAP." : "SHAP unavailable for this id."}
          </p>
        );
      }
      return <p className="text-xs text-exiqo-glow/50">No SHAP data available</p>;
    }
    return (
      <RiskStatePlaceholder
        loading={loading}
        error={error}
        empty={!loading && !error && !features.length}
        message="No SHAP data available"
      />
    );
  }

  const top = topFeatures(features, maxBars);
  const legendMuted = dark ? "text-exiqo-glow/45" : "text-gray-400";
  const headerMuted = dark ? "text-exiqo-glow/40" : "text-gray-400";

  return (
    <div className="space-y-2">
      <div className={`mb-1 flex gap-4 text-[10px] ${legendMuted}`}>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-3 rounded-sm bg-red-400 opacity-80" />
          Increases risk
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-3 rounded-sm bg-green-500 opacity-80" />
          Reduces risk
        </span>
      </div>

      <div className={`flex items-center gap-2 text-[10px] uppercase tracking-wide ${headerMuted}`}>
        <span className="w-32 shrink-0 text-right">Feature</span>
        <span className="flex-1">Impact</span>
        <span className="w-14 shrink-0 text-right">Value</span>
        <span className="w-14 shrink-0 text-right">SHAP</span>
      </div>

      {top.map((f, i) => (
        <Bar key={f.name} feature={f} index={i} dark={dark} />
      ))}
    </div>
  );
}
