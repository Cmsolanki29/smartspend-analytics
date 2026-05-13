import type { HTMLAttributes, ReactNode } from "react";

export type GlassCardProps = HTMLAttributes<HTMLDivElement> & {
  children: ReactNode;
  /** Visual elevation: "raised" adds extra glow + ring. */
  elevation?: "flat" | "raised";
  /** Inner padding scale. */
  padding?: "sm" | "md" | "lg";
  /**
   * "glass" — frosted intro-style (blur + translucent wash).
   * "panel" — near-opaque surface for tables / long text (no backdrop-blur).
   */
  surface?: "glass" | "panel";
};

const padMap = {
  sm: "p-4 md:p-5",
  md: "p-6 md:p-8",
  lg: "p-8 md:p-10",
};

/**
 * Glass token used across the intro flow.
 * `surface="glass"`: bg-white/5 backdrop-blur-2xl border border-white/10 rounded-2xl
 * `surface="panel"`: opaque-ish dashboard panels (sharp text, no stacked blur).
 */
export function GlassCard({
  children,
  elevation = "flat",
  padding = "md",
  surface = "glass",
  className,
  ...rest
}: GlassCardProps) {
  const elevationClass =
    elevation === "raised"
      ? "shadow-[0_18px_60px_rgba(124,58,237,0.28),0_0_0_1px_rgba(255,255,255,0.06)_inset,0_0_60px_rgba(34,211,238,0.10)]"
      : "shadow-ss-glass";

  const surfaceClass =
    surface === "panel"
      ? "border-white/10 bg-[#0c0c18]/95"
      : "border-white/10 bg-white/5 backdrop-blur-2xl";

  return (
    <div
      {...rest}
      className={`relative overflow-hidden rounded-2xl ${surfaceClass} ${elevationClass} ${padMap[padding]} ${className ?? ""}`}
    >
      {surface === "glass" ? (
        <div className="pointer-events-none absolute inset-0 rounded-2xl bg-gradient-to-br from-white/[0.06] via-transparent to-violet-500/[0.04]" />
      ) : null}
      <div className="relative">{children}</div>
    </div>
  );
}

export default GlassCard;
