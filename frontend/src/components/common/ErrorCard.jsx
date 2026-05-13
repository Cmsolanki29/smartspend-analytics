import React from "react";
import { AlertCircle, RefreshCw } from "lucide-react";
import { GlassCard } from "../intro/GlassCard";

export const ErrorCard = ({ message, onRetry }) => (
  <GlassCard padding="md" className="border-rose-500/30 shadow-[0_0_28px_rgba(244,63,94,0.15)]">
    <div className="flex flex-col items-center gap-3 text-center sm:flex-row sm:text-left">
      <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-rose-500/15 text-rose-300">
        <AlertCircle className="h-7 w-7" aria-hidden />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-rose-100">{message || "Something went wrong. Please try again."}</p>
        {onRetry ? (
          <button
            type="button"
            onClick={onRetry}
            className="mt-3 inline-flex min-h-[48px] items-center justify-center gap-2 rounded-xl border border-white/15 bg-white/[0.06] px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-white/[0.1] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60 md:min-h-0"
          >
            <RefreshCw className="h-4 w-4" aria-hidden />
            Retry
          </button>
        ) : null}
      </div>
    </div>
  </GlassCard>
);
