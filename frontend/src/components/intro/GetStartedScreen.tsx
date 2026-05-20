import { motion, useReducedMotion } from "framer-motion";
import { ArrowLeft, ArrowRight, BadgeCheck, Landmark, ShieldCheck } from "lucide-react";
import { AuroraBackground } from "./AuroraBackground";
import { GlassCard } from "./GlassCard";
import { GradientButton } from "./GradientButton";
import { ShieldMark } from "./ShieldMark";

const BRAND_EASE = [0.22, 1, 0.36, 1] as const;

export type GetStartedScreenProps = {
  onCreate: () => void;
  onSignIn: () => void;
  /** Demo: replay splash animation from the welcome screen. */
  onBackToSplash?: () => void;
  shieldLayoutId?: string;
};

export function GetStartedScreen({
  onCreate,
  onSignIn,
  onBackToSplash,
  shieldLayoutId = "ssShieldMark",
}: GetStartedScreenProps) {
  const reduce = useReducedMotion();

  return (
    <div className="relative flex min-h-[100dvh] w-full items-center justify-center overflow-hidden bg-[#070418] font-sans text-ss-ink">
      {/* Backdrop */}
      <AuroraBackground starCount={56} tone="cool" />

      {/* Huge rotating shield watermark @ 6% */}
      <div
        className={`pointer-events-none absolute inset-0 flex items-center justify-center opacity-[0.06] ${
          reduce ? "" : "animate-ss-spin-slow"
        }`}
        aria-hidden
      >
        <ShieldMark stage="complete" size={760} />
      </div>

      {/* Top mini navbar with morphing logo */}
      <header className="absolute inset-x-0 top-0 z-10 flex items-center justify-between px-5 pt-5 md:px-10 md:pt-7">
        {onBackToSplash ? (
          <button
            type="button"
            onClick={onBackToSplash}
            className="flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.05] px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.16em] text-white/75 backdrop-blur-md transition hover:border-white/25 hover:bg-white/[0.08] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60"
          >
            <ArrowLeft size={13} />
            Back
          </button>
        ) : (
          <span aria-hidden />
        )}
        <div className="flex items-center gap-2.5">
          {/* No layoutId — avoids Framer FLIP clash when Back replays splash. */}
          <ShieldMark stage="complete" size={36} />
          <span className="font-heading text-base font-semibold tracking-tight text-white">
            SmartSpend
          </span>
        </div>
      </header>

      {/* Centered glass card */}
      <motion.div
        className="relative z-10 w-full max-w-md px-5 md:max-w-lg"
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.65, ease: BRAND_EASE }}
      >
        <GlassCard padding="lg" elevation="raised" className="text-center">
          <motion.div
            className="mx-auto mb-6 flex h-16 w-16 items-center justify-center"
            initial={{ scale: 0.85, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ duration: 0.55, ease: BRAND_EASE, delay: 0.1 }}
          >
            <ShieldMark stage="complete" size={64} />
          </motion.div>

          <h1 className="font-heading text-[clamp(1.6rem,4.4vw,2.4rem)] font-semibold leading-[1.08] tracking-tight text-white">
            Welcome to the future of{" "}
            <span className="bg-ss-brand bg-[length:200%_200%] bg-clip-text text-transparent">
              your finances.
            </span>
          </h1>
          <p className="mx-auto mt-4 max-w-sm text-[15px] leading-relaxed text-ss-mute">
            Create your account in 30 seconds. No card required.
          </p>

          <div className="mt-8 flex flex-col gap-3">
            <GradientButton
              full
              onClick={onCreate}
              trailingIcon={<ArrowRight size={18} />}
            >
              Create my account
            </GradientButton>
            <GradientButton variant="ghost" full onClick={onSignIn}>
              I already have one
            </GradientButton>
          </div>

          {/* Trust row */}
          <div className="mt-9 grid grid-cols-3 gap-2 border-t border-white/[0.06] pt-6">
            <TrustItem icon={<ShieldCheck size={16} />} label="256-bit encryption" />
            <TrustItem icon={<Landmark size={16} />} label="RBI-aligned" />
            <TrustItem icon={<BadgeCheck size={16} />} label="ISO 27001" />
          </div>
        </GlassCard>

        <p className="mt-6 text-center text-[11px] uppercase tracking-[0.22em] text-white/40">
          Trusted by 10,000+ smart spenders
        </p>
      </motion.div>
    </div>
  );
}

function TrustItem({ icon, label }: { icon: React.ReactNode; label: string }) {
  return (
    <div className="flex flex-col items-center gap-1.5 text-center">
      <span className="flex h-9 w-9 items-center justify-center rounded-full border border-white/10 bg-white/[0.04] text-cyan-300 backdrop-blur-md">
        {icon}
      </span>
      <span className="text-[10.5px] font-medium uppercase tracking-[0.12em] text-white/65">
        {label}
      </span>
    </div>
  );
}

export default GetStartedScreen;
