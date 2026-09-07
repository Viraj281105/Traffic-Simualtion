import { useEffect, useRef, useState, useCallback } from "react";

/**
 * useContainerSize – Returns the live pixel dimensions of the element
 * attached via the returned ref. Recalculates on every ResizeObserver entry.
 */
export function useContainerSize<T extends HTMLElement = HTMLDivElement>(): [
  React.RefObject<T>,
  { width: number; height: number },
] {
  const ref = useRef<T>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });

  const measure = useCallback(() => {
    if (!ref.current) return;
    const { clientWidth, clientHeight } = ref.current;
    if (clientWidth > 0 && clientHeight > 0) {
      setSize({ width: clientWidth, height: clientHeight });
    }
  }, []);

  useEffect(() => {
    measure();
    const ro = new ResizeObserver(measure);
    if (ref.current) ro.observe(ref.current);
    return () => {
      ro.disconnect();
    };
  }, [measure]);

  return [ref as React.RefObject<T>, size];
}
