import React, { ReactNode } from "react";
import { LucideIcon } from "lucide-react";
import { GlassCard } from "../../intro/GlassCard";

export type EmptyHeroProps = {
  icon: LucideIcon;
  title: string;
  body: string;
  cta?: ReactNode;
  accentHex?: string;
};

export function EmptyHero({ icon: Icon, title, body, cta, accentHex = "#A78BFA" }: EmptyHeroProps) {
  return (
    <GlassCard padding="lg" className="border-white/[0.08] text-center">
      <div
        className="mx-auto mb-5 grid h-16 w-16 place-items-center rounded-2xl"
        style={{ background: `linear-gradient(135deg, rgba(124,58,237,0.3), ${accentHex}44)`, boxShadow: `0 0 32px ${accentHex}33` }}
      >
        <Icon className="h-8 w-8 text-white/80" aria-hidden />
      </div>
      <h3 className="font-heading text-lg font-semibold text-white">{title}</h3>
      <p className="mx-auto mt-2 max-w-sm text-sm leading-relaxed text-white/55">{body}</p>
      {cta && <div className="mt-6 flex justify-center">{cta}</div>}
    </GlassCard>
  );
}

export default EmptyHero;
