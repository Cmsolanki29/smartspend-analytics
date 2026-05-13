import React from "react";
import { Settings } from "lucide-react";
import { GlassCard } from "../intro/GlassCard";

export default function SettingsTab() {
  return (
    <GlassCard padding="lg" className="mx-auto mt-4 max-w-lg border-dashed border-white/15">
      <div className="flex items-start gap-3">
        <Settings className="mt-0.5 h-6 w-6 text-exiqo-glow" aria-hidden />
        <div>
          <h2 className="font-heading text-lg font-semibold text-white">Settings</h2>
          <p className="mt-2 text-sm text-exiqo-glow/70">
            Account preferences, data export, and notifications will land here. Use the month switcher in the top bar for now.
          </p>
          <p className="mt-3 inline-flex rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-[11px] font-semibold uppercase tracking-wide text-exiqo-glow/80">
            Coming soon
          </p>
        </div>
      </div>
    </GlassCard>
  );
}
