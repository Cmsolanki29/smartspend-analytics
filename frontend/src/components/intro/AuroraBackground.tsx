import { motion, useReducedMotion } from "framer-motion";
import { useMemo } from "react";

export type AuroraBackgroundProps = {
  /** Tone the orbs warmer (e.g. for splash) or cooler (e.g. for auth). */
  tone?: "default" | "warm" | "cool";
  /** Density of the starfield (0 = no stars). */
  starCount?: number;
  className?: string;
  /**
   * "full" — intro/splash depth (veil + vignette).
   * "app" — lighter atmospheric stack behind opaque dashboard panels (less milky wash).
   */
  variant?: "full" | "app";
};

const BRAND_EASE = [0.22, 1, 0.36, 1] as const;

/**
 * Layered ambient backdrop reused across every intro screen:
 * - Deep gradient base (#070418 → #0F0A2E)
 * - Two slowly drifting brand-colored orbs at low opacity
 * - Subtle starfield (twinkling SVG dots)
 *
 * Honors prefers-reduced-motion (no orb drift / twinkle).
 */
export function AuroraBackground({
  tone = "default",
  starCount = 48,
  className,
  variant = "full",
}: AuroraBackgroundProps) {
  const reduce = useReducedMotion();
  const appShell = variant === "app";

  const stars = useMemo(
    () =>
      Array.from({ length: starCount }, (_, i) => {
        const a = Math.sin(i * 12.9898) * 43758.5453;
        const b = Math.cos(i * 4.2 + 1.1) * 8123.4;
        return {
          id: i,
          left: ((a - Math.floor(a)) * 100).toFixed(2),
          top: ((b - Math.floor(b)) * 100).toFixed(2),
          size: 1 + (i % 3),
          delay: ((i % 11) * 0.32).toFixed(2),
        };
      }),
    [starCount]
  );

  const orbA =
    tone === "warm"
      ? "from-fuchsia-500/35 to-pink-500/15"
      : tone === "cool"
      ? "from-cyan-400/30 to-violet-500/15"
      : "from-violet-500/35 to-pink-500/10";
  const orbB =
    tone === "warm"
      ? "from-violet-500/25 to-cyan-400/10"
      : tone === "cool"
      ? "from-violet-500/30 to-cyan-400/15"
      : "from-cyan-400/22 to-fuchsia-500/10";

  return (
    <div
      className={`pointer-events-none absolute inset-0 z-0 overflow-hidden ${className ?? ""}`}
      aria-hidden
    >
      {/* Base gradient */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_120%_85%_at_50%_-10%,rgba(124,58,237,0.18),transparent_55%)] bg-gradient-to-br from-[#070418] via-[#0F0A2E] to-[#06030F]" />

      {/* Drifting orbs */}
      <motion.div
        className={`absolute -left-24 top-[8%] h-[28rem] w-[28rem] rounded-full bg-gradient-to-br ${orbA} blur-[140px]`}
        animate={
          reduce
            ? undefined
            : { x: [0, 60, -20, 0], y: [0, -40, 30, 0], scale: [1, 1.08, 0.96, 1] }
        }
        transition={{ duration: 18, repeat: Infinity, ease: "easeInOut" }}
      />
      <motion.div
        className={`absolute -right-32 bottom-[6%] h-[32rem] w-[32rem] rounded-full bg-gradient-to-tr ${orbB} blur-[150px]`}
        animate={
          reduce
            ? undefined
            : { x: [0, -50, 30, 0], y: [0, 40, -20, 0], scale: [1, 1.1, 0.94, 1] }
        }
        transition={{ duration: 22, repeat: Infinity, ease: "easeInOut", delay: 1.4 }}
      />

      {/* Soft veil — toned down in app shell so opaque cards are not fighting a heavy wash */}
      <div
        className={
          appShell
            ? "absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-[#070418]/22"
            : "absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-[#070418]/65"
        }
      />

      {/* Conic light wash */}
      <motion.div
        className="absolute -left-1/4 top-0 h-full w-[150%] opacity-[0.06]"
        style={{
          background:
            "conic-gradient(from 200deg at 50% 45%, transparent 0deg, rgba(124,58,237,0.5) 48deg, transparent 100deg, rgba(34,211,238,0.35) 190deg, transparent 280deg)",
        }}
        animate={reduce ? undefined : { rotate: 360 }}
        transition={{ duration: 160, repeat: Infinity, ease: "linear" }}
      />

      {/* Starfield */}
      {stars.length > 0 && (
        <svg
          className="absolute inset-0 h-full w-full"
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
        >
          {stars.map((s) => (
            <circle
              key={s.id}
              cx={s.left}
              cy={s.top}
              r={s.size * 0.05}
              fill="#F5F3FF"
              className={reduce ? "" : "animate-ss-twinkle"}
              style={{
                opacity: reduce ? 0.45 : undefined,
                animationDelay: `${s.delay}s`,
                transformOrigin: "center",
                transition: `opacity 0.6s cubic-bezier(${BRAND_EASE.join(",")})`,
              }}
            />
          ))}
        </svg>
      )}

      {/* Vignette */}
      <div
        className={
          appShell
            ? "absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_62%,rgba(7,4,24,0.22)_100%)]"
            : "absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_55%,rgba(7,4,24,0.6)_100%)]"
        }
      />
    </div>
  );
}

export default AuroraBackground;
