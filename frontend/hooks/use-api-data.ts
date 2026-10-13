"use client";

import { useCallback, useEffect, useState } from "react";

export function useApiData<T>(loader: () => Promise<T>, _legacyDependencies?: readonly unknown[]) {
  void _legacyDependencies;
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await loader());
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "정보를 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }, [loader]);
  useEffect(() => { void load(); }, [load]);
  return { data, error, loading, refresh: load };
}
