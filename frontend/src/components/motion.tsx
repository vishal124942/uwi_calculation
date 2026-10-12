"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";

const REDUCED = "(prefers-reduced-motion: reduce)";

function subscribeReduced(onChange: () => void) {
  const mq = window.matchMedia(REDUCED);
  mq.addEventListener("change", onChange);
  return () => mq.removeEventListener("change", onChange);
}

export function useReducedMotion(): boolean {
  return useSyncExternalStore(subscribeReduced, () => window.matchMedia(REDUCED).matches, () => false);
}

/** Eases from the previously shown value to `value`; starts from 0 on first mount. */
export function useCountUp(value: number, duration = 900): number {
  const reduced = useReducedMotion();
  const [shown, setShown] = useState(0);
  const from = useRef(0);
  useEffect(() => {
    let raf = 0;
    const start = performance.now();
    const origin = from.current;
    const tick = (now: number) => {
      const t = reduced ? 1 : Math.min(1, (now - start) / duration);
      const v = origin + (value - origin) * (1 - Math.pow(1 - t, 3));
      from.current = v;
      setShown(v);
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, duration, reduced]);
  return shown;
}

export function CountUp({ value, format, duration }: { value: number; format: (n: number) => string; duration?: number }) {
  return <span className="tabular">{format(useCountUp(value, duration))}</span>;
}

/** Feeds the pointer position to the hovered `.spotlight` element as --mx / --my (drives its glow in globals.css). */
export function useSpotlight() {
  useEffect(() => {
    const move = (e: PointerEvent) => {
      const el = (e.target as Element | null)?.closest?.(".spotlight") as HTMLElement | null;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      el.style.setProperty("--mx", `${e.clientX - rect.left}px`);
      el.style.setProperty("--my", `${e.clientY - rect.top}px`);
    };
    window.addEventListener("pointermove", move, { passive: true });
    return () => window.removeEventListener("pointermove", move);
  }, []);
}
