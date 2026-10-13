"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export function usePolling<T>(
  loader: () => Promise<T>,
  shouldPoll: (value: T) => boolean,
  intervalMs = 5000
) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  const load = useCallback(async () => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    try {
      const next = await loader();
      if (!mountedRef.current) return;
      setData(next);
      setError(null);
      if (shouldPoll(next) && document.visibilityState === "visible") {
        timeoutRef.current = setTimeout(load, intervalMs);
      }
    } catch (caught) {
      if (!mountedRef.current) return;
      setError(caught instanceof Error ? caught.message : "상태를 불러오지 못했습니다.");
      if (document.visibilityState === "visible") {
        timeoutRef.current = setTimeout(load, Math.min(intervalMs * 3, 30000));
      }
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, [intervalMs, loader, shouldPoll]);

  useEffect(() => {
    mountedRef.current = true;
    void load();
    const onVisibility = () => {
      if (document.visibilityState === "visible") void load();
      else if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      mountedRef.current = false;
      document.removeEventListener("visibilitychange", onVisibility);
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, [load]);

  return { data, error, loading, refresh: load };
}
