import React from "react";
import { Minus, TrendingDown, TrendingUp } from "lucide-react";

export type DeltaChipProps = {
  delta?: number | null;
  suffix?: string;
};

export function DeltaChip({ delta, suffix = "%" }: DeltaChipProps) {
  if (delta == null) return null;
  const pos = delta > 0;
  const zero = delta === 0;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold tabular-nums ${
        zero ? "bg-white/[0.06] text-white/50" : pos ? "bg-emerald-500/15 text-emerald-300" : "bg-rose-500/15 text-rose-300"
      }`}
    >
      {zero ? (
        <Minus className="h-3 w-3" aria-hidden />
      ) : pos ? (
        <TrendingUp className="h-3 w-3" aria-hidden />
      ) : (
        <TrendingDown className="h-3 w-3" aria-hidden />
      )}
      {pos ? "+" : ""}
      {Math.abs(delta).toFixed(1)}
      {suffix}
    </span>
  );
}

export default DeltaChip;
