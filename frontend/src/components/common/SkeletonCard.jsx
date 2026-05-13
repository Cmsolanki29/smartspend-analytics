import React from "react";
import { GlassCard } from "../intro/GlassCard";

export const SkeletonCard = ({ lines = 3, height = 120 }) => (
  <GlassCard padding="sm" className="animate-ss-shimmer border-white/[0.06] bg-[linear-gradient(110deg,rgba(255,255,255,0.04)_8%,rgba(255,255,255,0.09)_18%,rgba(255,255,255,0.04)_33%)] bg-[length:200%_100%]">
    <div className="space-y-3" style={{ minHeight: height }}>
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} className="h-2.5 rounded-full bg-white/[0.08]" style={{ width: `${Math.max(40, 85 - i * 15)}%` }} />
      ))}
    </div>
  </GlassCard>
);

export const SkeletonStats = () => (
  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
    {Array.from({ length: 4 }, (_, i) => (
      <SkeletonCard key={i} lines={2} height={100} />
    ))}
  </div>
);
