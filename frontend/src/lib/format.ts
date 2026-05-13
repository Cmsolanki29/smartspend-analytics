import { useEffect, useState } from "react";

/** Indian-locale currency formatter — ₹1,00,000 style. */
export function inr(value: number | string | null | undefined): string {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(Number(value || 0));
}

/** Compact Indian formatting: ₹12.5L, ₹2.1Cr, ₹4.5K. */
export function inrCompact(value: number | string | null | undefined): string {
  const n = Number(value || 0);
  if (n >= 10_000_000) return `₹${(n / 10_000_000).toFixed(1)}Cr`;
  if (n >= 100_000)    return `₹${(n / 100_000).toFixed(1)}L`;
  if (n >= 1_000)      return `₹${(n / 1_000).toFixed(0)}K`;
  return inr(n);
}

/**
 * Animates a number from 0 → target on mount.
 * Respects prefers-reduced-motion: instantly returns target when motion is reduced.
 */
export function useCountUp(target: number, duration = 900): number {
  const prefersReduced =
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const [value, setValue] = useState(prefersReduced ? target : 0);

  useEffect(() => {
    if (prefersReduced || target === 0) { setValue(target); return; }
    let startTime: number | null = null;
    const initial = 0;
    const diff = target - initial;

    const tick = (ts: number) => {
      if (!startTime) startTime = ts;
      const progress = Math.min((ts - startTime) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
      setValue(Math.round(initial + diff * eased));
      if (progress < 1) requestAnimationFrame(tick);
    };

    const raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, duration, prefersReduced]);

  return value;
}
