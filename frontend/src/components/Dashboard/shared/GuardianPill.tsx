import { motion, useReducedMotion } from "framer-motion";
import type { LucideIcon } from "lucide-react";
import { ChevronRight } from "lucide-react";
import { GlassCard } from "../../intro/GlassCard";

export type GuardianGlow = "rose" | "amber" | "violet" | "cyan";

const glowMap: Record<
  GuardianGlow,
  { ring: string; shadow: string; border: string }
> = {
  rose: {
    ring: "hover:shadow-[0_0_28px_rgba(244,63,94,0.35)]",
    shadow: "shadow-[0_0_20px_rgba(244,63,94,0.2)]",
    border: "border-rose-500/35",
  },
  amber: {
    ring: "hover:shadow-[0_0_28px_rgba(245,158,11,0.35)]",
    shadow: "shadow-[0_0_20px_rgba(245,158,11,0.2)]",
    border: "border-amber-500/35",
  },
  violet: {
    ring: "hover:shadow-[0_0_28px_rgba(167,139,250,0.35)]",
    shadow: "shadow-[0_0_20px_rgba(124,58,237,0.25)]",
    border: "border-exiqo-purple/40",
  },
  cyan: {
    ring: "hover:shadow-[0_0_28px_rgba(34,211,238,0.35)]",
    shadow: "shadow-[0_0_20px_rgba(34,211,238,0.22)]",
    border: "border-cyan-400/35",
  },
};

export type GuardianPillProps = {
  label: string;
  sub: string;
  icon: LucideIcon;
  glow: GuardianGlow;
  onClick?: () => void;
  disabled?: boolean;
  delay?: number;
};

export function GuardianPill({ label, sub, icon: Icon, glow, onClick, disabled, delay = 0 }: GuardianPillProps) {
  const reduce = useReducedMotion();
  const g = glowMap[glow];
  return (
    <motion.button
      type="button"
      disabled={disabled}
      onClick={onClick}
      initial={reduce ? false : { opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: reduce ? 0.12 : 0.4, ease: [0.22, 1, 0.36, 1], delay: reduce ? 0 : delay }}
      whileHover={reduce || disabled ? undefined : { y: -4, scale: 1.02 }}
      whileTap={disabled ? undefined : { scale: 0.98 }}
      className={`group min-h-[48px] w-full text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60 disabled:opacity-50 ${g.ring}`}
    >
      <GlassCard
        padding="sm"
        className={`!p-4 transition-all duration-500 ease-brand ${g.border} ${g.shadow} group-hover:border-white/20 group-hover:bg-white/[0.08]`}
      >
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-white/[0.06] text-exiqo-glow group-hover:text-white">
            <Icon className="h-5 w-5" aria-hidden />
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-xs font-semibold text-white">{label}</p>
            <p className="truncate text-[11px] text-exiqo-glow/65">{sub}</p>
          </div>
          <ChevronRight className="h-4 w-4 shrink-0 text-exiqo-glow/40 transition group-hover:translate-x-0.5 group-hover:text-exiqo-glow" aria-hidden />
        </div>
      </GlassCard>
    </motion.button>
  );
}

export default GuardianPill;
