import { useEffect, useRef, useState } from "react";

export function useCountUp(target, { durationMs = 900, enabled = true } = {}) {
  const [value, setValue] = useState(0);
  const displayedRef = useRef(0);

  useEffect(() => {
    const t = Number(target);
    if (!Number.isFinite(t)) {
      setValue(0);
      displayedRef.current = 0;
      return undefined;
    }
    if (!enabled) {
      setValue(t);
      displayedRef.current = t;
      return undefined;
    }

    const from = displayedRef.current;
    let start = null;
    let frame;

    const step = (now) => {
      if (start == null) start = now;
      const p = Math.min(1, (now - start) / durationMs);
      const eased = 1 - (1 - p) ** 3;
      const next = from + (t - from) * eased;
      displayedRef.current = next;
      setValue(next);
      if (p < 1) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [target, durationMs, enabled]);

  return value;
}
