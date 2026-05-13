import React, { useMemo, useId } from "react";
import { motion } from "framer-motion";

/** Tiny sparkline from a seed number (deterministic fake history for demo). */
export function MiniSparkline({ seed = 0, className = "" }) {
  const gid = useId().replace(/:/g, "");
  const pts = useMemo(() => {
    const n = 12;
    const out = [];
    let v = 0.35 + ((seed * 9301 + 49297) % 2333) / 23330;
    for (let i = 0; i < n; i += 1) {
      v = Math.min(0.95, Math.max(0.08, v + (Math.sin(seed + i * 1.7) * 0.12 + (i % 3) * 0.02 - 0.03)));
      out.push(v);
    }
    return out;
  }, [seed]);

  const w = 120;
  const h = 36;
  const pad = 2;
  const denom = Math.max(1, pts.length - 1);
  const d = useMemo(() => {
    if (!pts.length) return "";
    return pts
      .map((p, i) => {
        const x = pad + (i / denom) * (w - pad * 2);
        const y = pad + (1 - p) * (h - pad * 2);
        return `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
      })
      .join(" ");
  }, [pts, w, h, denom]);

  return (
    <svg className={className} width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden>
      <defs>
        <linearGradient id={`sparkGrad-${gid}`} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#7c3aed" stopOpacity="0.9" />
          <stop offset="100%" stopColor="#2563eb" stopOpacity="0.9" />
        </linearGradient>
      </defs>
      <motion.path
        d={d}
        fill="none"
        stroke={`url(#sparkGrad-${gid})`}
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        initial={{ pathLength: 0, opacity: 0 }}
        animate={{ pathLength: 1, opacity: 1 }}
        transition={{ duration: 1.1, ease: [0.22, 1, 0.36, 1] }}
      />
    </svg>
  );
}
