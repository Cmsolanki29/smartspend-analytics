import React, { useEffect, useRef } from "react";

type Particle = {
  x: number; y: number; vx: number; vy: number;
  r: number; alpha: number; color: string;
};

const PALETTE = ["#7C3AED", "#EC4899", "#22D3EE", "#A78BFA", "#F59E0B", "#10B981", "#F43F5E"];

export type ConfettiBurstProps = {
  /** Set to true to trigger burst; reset to false to re-trigger on next true. */
  trigger: boolean;
  /** Canvas size in px (square). Default 200. */
  size?: number;
};

/**
 * 18-particle confetti canvas burst. Fades over ~1.4 s.
 * Respects prefers-reduced-motion: renders nothing when motion is reduced.
 */
export function ConfettiBurst({ trigger, size = 200 }: ConfettiBurstProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rafRef = useRef<number>(0);

  useEffect(() => {
    if (!trigger) return;
    if (typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const particles: Particle[] = Array.from({ length: 18 }, () => ({
      x: size / 2,
      y: size / 2,
      vx: (Math.random() - 0.5) * 8,
      vy: Math.random() * -10 - 3,
      r: Math.random() * 5 + 3,
      alpha: 1,
      color: PALETTE[Math.floor(Math.random() * PALETTE.length)],
    }));

    const draw = () => {
      ctx.clearRect(0, 0, size, size);
      particles.forEach((p) => {
        p.x  += p.vx;
        p.y  += p.vy;
        p.vy += 0.35; // gravity
        p.alpha -= 0.016;
        if (p.alpha <= 0) return;
        ctx.save();
        ctx.globalAlpha = Math.max(0, p.alpha);
        ctx.fillStyle = p.color;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
      });
      if (particles.some((p) => p.alpha > 0)) {
        rafRef.current = requestAnimationFrame(draw);
      } else {
        ctx.clearRect(0, 0, size, size);
      }
    };

    rafRef.current = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(rafRef.current);
  }, [trigger, size]);

  return (
    <canvas
      ref={canvasRef}
      width={size}
      height={size}
      className="pointer-events-none absolute inset-0 z-50"
      aria-hidden
    />
  );
}

export default ConfettiBurst;
