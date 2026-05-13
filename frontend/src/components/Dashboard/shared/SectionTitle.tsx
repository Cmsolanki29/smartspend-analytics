import React, { ReactNode } from "react";

export type SectionTitleProps = {
  eyebrow?: string;
  title: string;
  accentHex?: string;
  actions?: ReactNode;
};

export function SectionTitle({ eyebrow, title, accentHex, actions }: SectionTitleProps) {
  return (
    <div className="mb-4 flex items-end justify-between gap-4">
      <div className="min-w-0">
        {eyebrow && (
          <p
            className="mb-1 text-[10px] font-semibold uppercase tracking-[0.18em]"
            style={{ color: accentHex ? `${accentHex}bb` : "rgba(167,139,250,0.7)" }}
          >
            {eyebrow}
          </p>
        )}
        <h2 className="font-heading text-base font-semibold text-white sm:text-lg">{title}</h2>
      </div>
      {actions && <div className="shrink-0">{actions}</div>}
    </div>
  );
}

export default SectionTitle;
