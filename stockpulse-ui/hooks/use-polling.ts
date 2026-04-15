"use client";
import { useState, useEffect, useCallback, useRef } from "react";

export function usePolling<T>(
  fetcher: () => Promise<T>,
  intervalMs: number = 30000
) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const fetcherRef = useRef(fetcher);
  const inFlightRef = useRef(false);
  const visibleRef = useRef(true);
  fetcherRef.current = fetcher;

  const refresh = useCallback(async () => {
    // Skip if a fetch is already in progress or tab is hidden
    if (inFlightRef.current) return;
    if (!visibleRef.current) return;

    inFlightRef.current = true;
    try {
      const result = await fetcherRef.current();
      setData(result);
      setError(null);
    } catch (e: any) {
      setError(e.message || "Failed to fetch");
    } finally {
      setLoading(false);
      inFlightRef.current = false;
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, intervalMs);

    // Pause polling when tab is hidden, resume when visible
    const onVisibility = () => {
      visibleRef.current = !document.hidden;
      if (!document.hidden) refresh();
    };
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      clearInterval(id);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [refresh, intervalMs]);

  return { data, loading, error, refresh };
}
