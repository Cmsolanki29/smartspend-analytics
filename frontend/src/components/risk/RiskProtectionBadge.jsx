/**
 * RiskProtectionBadge — always-visible status badge (top of header/sidebar).
 * Shows 8-phase shield when risk engine is healthy, or a muted offline pill.
 * Clicking it opens FraudShield (unified protection hub).
 */

import React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ShieldCheck, ShieldOff } from "lucide-react";
import { useRisk } from "../../contexts/RiskContext";

export function RiskProtectionBadge({ onNavigate, compact = false }) {
  const { healthy, lastCheckedAt } = useRisk();

  const pulseRing = healthy ? "bg-green-400" : "bg-gray-400";
  const label     = healthy ? "Protected" : "Engine offline";
  const bg        = healthy ? "bg-green-50 border-green-200 text-green-700"
                            : "bg-gray-50  border-gray-200  text-gray-400";

  return (
    <motion.button
      onClick={() => onNavigate?.("fraud")}
      whileHover={{ scale: 1.03 }}
      whileTap={{ scale: 0.97 }}
      className={`
        inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-medium
        transition-colors cursor-pointer select-none ${bg}
      `}
      title={
        lastCheckedAt
          ? `8-Phase Fraud Engine · ${healthy ? "Online" : "Offline"} · checked ${new Date(lastCheckedAt).toLocaleTimeString()}`
          : "8-Phase Fraud Engine"
      }
    >
      {/* Pulsing dot */}
      <span className="relative flex h-2 w-2">
        <AnimatePresence>
          {healthy && (
            <motion.span
              key="ping"
              initial={{ scale: 0.8, opacity: 0.8 }}
              animate={{ scale: 2, opacity: 0 }}
              transition={{ repeat: Infinity, duration: 1.5 }}
              className={`absolute inline-flex h-full w-full rounded-full ${pulseRing}`}
            />
          )}
        </AnimatePresence>
        <span className={`relative inline-flex rounded-full h-2 w-2 ${pulseRing}`} />
      </span>

      {healthy ? (
        <ShieldCheck size={12} className="shrink-0" />
      ) : (
        <ShieldOff size={12} className="shrink-0" />
      )}

      {!compact && <span>{label}</span>}
    </motion.button>
  );
}
