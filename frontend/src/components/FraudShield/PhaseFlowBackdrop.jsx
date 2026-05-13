import React from "react";
import { motion } from "framer-motion";

/** Decorative animated “data flow” curves behind the phase grid (desktop). */
export function PhaseFlowBackdrop() {
  return (
    <svg
      className="pointer-events-none absolute inset-0 hidden h-full w-full opacity-[0.22] lg:block"
      preserveAspectRatio="none"
      aria-hidden
    >
      <defs>
        <linearGradient id="phaseFlowGrad" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#7c3aed" />
          <stop offset="55%" stopColor="#22d3ee" />
          <stop offset="100%" stopColor="#2563eb" />
        </linearGradient>
      </defs>
      <motion.path
        d="M -2% 38% C 18% 18%, 38% 52%, 52% 34% S 78% 22%, 102% 44%"
        fill="none"
        stroke="url(#phaseFlowGrad)"
        strokeWidth={1.25}
        strokeLinecap="round"
        strokeDasharray="7 12"
        initial={{ strokeDashoffset: 0 }}
        animate={{ strokeDashoffset: -200 }}
        transition={{ duration: 22, repeat: Infinity, ease: "linear" }}
      />
      <motion.path
        d="M 102% 62% C 72% 78%, 48% 48%, 28% 66% S 8% 88%, -4% 58%"
        fill="none"
        stroke="url(#phaseFlowGrad)"
        strokeWidth={1}
        strokeOpacity={0.65}
        strokeLinecap="round"
        strokeDasharray="5 14"
        initial={{ strokeDashoffset: 0 }}
        animate={{ strokeDashoffset: 180 }}
        transition={{ duration: 26, repeat: Infinity, ease: "linear" }}
      />
    </svg>
  );
}
