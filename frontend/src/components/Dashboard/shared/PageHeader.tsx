import React, { ReactNode } from "react";

export type PageHeaderProps = {
  eyebrow: string;
  title: string;
  subtitle?: string;
  rightSlot?: ReactNode;
  /** Accent hex colour for gradient title and eyebrow. */
  accentHex: string;
};

/**
 * Universal premium page header.
 * Left: identity bar pill → eyebrow → gradient title → subtitle.
 * Right: HeroKpiTile slot.
 * Spec: clamp(1.75rem, 3.5vw, 2.5rem) title, font-heading font-semibold.
 */
export function PageHeader({ eyebrow, title, subtitle, rightSlot, accentHex }: PageHeaderProps) {
  return (
    <div className="mb-8 flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
      {/* Left: identity bar + text */}
      <div className="min-w-0 flex-1">
        {/* 4 px gradient identity bar above the title */}
        <div
          className="mb-4 h-1 w-12 rounded-full"
          style={{ background: `linear-gradient(90deg, #7C3AED, ${accentHex})` }}
          aria-hidden
        />

        <p
          className="mb-2 text-[11px] font-semibold uppercase tracking-[0.18em]"
          style={{ color: `${accentHex}cc` }}
        >
          {eyebrow}
        </p>

        <h1
          className="font-heading font-semibold leading-tight tracking-tight text-white"
          style={{
            fontSize: "clamp(1.75rem, 3.5vw, 2.5rem)",
            background: `linear-gradient(135deg, #ffffff 40%, ${accentHex})`,
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
            backgroundClip: "text",
          }}
        >
          {title}
        </h1>

        {subtitle && (
          <p className="mt-3 max-w-xl text-[15px] leading-relaxed text-white/65">{subtitle}</p>
        )}
      </div>

      {/* Right: hero KPI tile slot */}
      {rightSlot && (
        <div className="shrink-0 lg:ml-6">{rightSlot}</div>
      )}
    </div>
  );
}

export default PageHeader;
