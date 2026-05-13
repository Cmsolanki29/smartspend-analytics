import React from "react";

/**
 * @param {{ icon?: React.ReactNode; title: string; subtitle?: string; action?: React.ReactNode }} props
 */
export const EmptyState = ({ icon, title, subtitle, action }) => (
  <div className="px-6 py-10 text-center text-exiqo-glow/70">
    <div className="mb-4 flex justify-center text-exiqo-glow/50" aria-hidden>
      {icon && typeof icon !== "string" ? icon : null}
      {typeof icon === "string" ? <span className="text-4xl">{icon}</span> : null}
      {!icon ? <span className="text-4xl opacity-40">—</span> : null}
    </div>
    <div className="text-base font-semibold text-white/90">{title}</div>
    {subtitle ? <div className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-exiqo-glow/65">{subtitle}</div> : null}
    {action ? <div className="mt-5">{action}</div> : null}
  </div>
);
