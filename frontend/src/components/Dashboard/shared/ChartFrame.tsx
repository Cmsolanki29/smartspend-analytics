import React, { ReactNode } from "react";
import { GlassCard } from "../../intro/GlassCard";

export type ChartFrameProps = {
  title: string;
  eyebrow?: string;
  accentHex?: string;
  legend?: { label: string; color: string }[];
  children: ReactNode;
  className?: string;
  actions?: ReactNode;
};

export function ChartFrame({ title, eyebrow, accentHex, legend, children, className, actions }: ChartFrameProps) {
  return (
    <GlassCard padding="sm" elevation="flat" className={`border-white/[0.08] ${className ?? ""}`}>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          {eyebrow && (
            <p className="mb-1 text-[10px] font-semibold uppercase tracking-[0.18em]" style={{ color: accentHex ? `${accentHex}bb` : "rgba(167,139,250,0.7)" }}>
              {eyebrow}
            </p>
          )}
          <h3 className="font-heading text-sm font-semibold text-white sm:text-[15px]">{title}</h3>
        </div>
        <div className="flex shrink-0 items-center gap-4">
          {legend?.map((item) => (
            <span key={item.label} className="flex items-center gap-1.5 text-[11px] text-white/50">
              <span className="h-2 w-2 rounded-full" style={{ background: item.color }} aria-hidden />
              {item.label}
            </span>
          ))}
          {actions}
        </div>
      </div>
      {children}
    </GlassCard>
  );
}

export default ChartFrame;
