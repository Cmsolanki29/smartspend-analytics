import React, { useMemo } from "react";
import { motion } from "framer-motion";

const DEFAULT_SIZE = 112;
const DEFAULT_STROKE = 8;

function polarToCartesian(cx, cy, r, angleDeg) {
  const rad = ((angleDeg - 90) * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

export function TrustRing({
  score,
  max = 100,
  size = DEFAULT_SIZE,
  stroke = DEFAULT_STROKE,
  label,
  sublabel,
  className = "",
  dark = true,
}) {
  const pct = Math.min(100, Math.max(0, (Number(score) / max) * 100));
  const strokeColor = useMemo(() => {
    if (pct >= 80) return "#10b981";
    if (pct >= 55) return "#f59e0b";
    return "#ef4444";
  }, [pct]);

  const r = (size - stroke) / 2;
  const c = size / 2;
  const start = polarToCartesian(c, c, r, 0);
  const endPt = polarToCartesian(c, c, r, (pct / 100) * 360);
  const large = pct > 50 ? 1 : 0;
  const d = `M ${start.x} ${start.y} A ${r} ${r} 0 ${large} 1 ${endPt.x} ${endPt.y}`;
  const trackStroke = dark ? "rgba(255,255,255,0.08)" : "#e5e7eb";
  const numCls = dark ? "text-2xl font-bold tabular-nums tracking-tight text-white" : "text-2xl font-bold tabular-nums tracking-tight text-gray-900";
  const labelCls = dark
    ? "text-[9px] font-medium uppercase tracking-wider text-exiqo-glow/50"
    : "text-[9px] font-medium uppercase tracking-wider text-gray-500";
  const subCls = dark ? "mt-0.5 max-w-[5.5rem] text-[9px] leading-tight text-exiqo-glow/45" : "mt-0.5 max-w-[5.5rem] text-[9px] leading-tight text-gray-500";

  return (
    <div className={`relative inline-flex flex-col items-center ${className}`} style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90" aria-hidden>
        <circle cx={c} cy={c} r={r} fill="none" stroke={trackStroke} strokeWidth={stroke} />
        <motion.path
          d={d}
          fill="none"
          stroke={strokeColor}
          strokeWidth={stroke}
          strokeLinecap="round"
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration: 1, ease: [0.22, 1, 0.36, 1] }}
        />
      </svg>
      <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center text-center">
        <span className={numCls}>{Math.round(pct)}</span>
        {label ? <span className={labelCls}>{label}</span> : null}
        {sublabel ? <span className={subCls}>{sublabel}</span> : null}
      </div>
    </div>
  );
}

/** 0–1 trust score → ring (same visual language as score/100). */
export function TrustRing01({ trust01, dark = true, ...rest }) {
  return <TrustRing score={(Number(trust01) || 0) * 100} max={100} label="Trust" dark={dark} {...rest} />;
}
