import { useCallback, useEffect, useRef, useState } from "react";

export interface PollingResult<T> {
  data: T | null;
  error: Error | null;
  /** true until the very first successful (or failed) fetch resolves */
  loading: boolean;
  /** true when at least one fetch has succeeded but the latest one errored */
  reconnecting: boolean;
  /** trigger an immediate out-of-band refetch */
  refresh: () => void;
}

/**
 * Polls `fetcher` every `intervalMs`. Never throws on network errors:
 * instead it keeps the last good `data` and surfaces `error`/`reconnecting`
 * so the UI can show a subtle "reconnecting…" state. Safe during API restarts
 * (e.g. while a reset/retrain is in flight).
 */
export function usePolling<T>(
  fetcher: () => Promise<T>,
  intervalMs = 2000,
  enabled = true
): PollingResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  // Keep the latest fetcher in a ref so changing closures (e.g. selected user)
  // don't restart the interval timer, but always use the freshest fetcher.
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const hasSucceeded = useRef(false);
  const mounted = useRef(true);
  const tick = useRef(0);

  const run = useCallback(async () => {
    const myTick = ++tick.current;
    try {
      const result = await fetcherRef.current();
      // Ignore stale responses (a newer fetch started while this was pending).
      if (!mounted.current || myTick !== tick.current) return;
      setData(result);
      setError(null);
      hasSucceeded.current = true;
    } catch (err) {
      if (!mounted.current || myTick !== tick.current) return;
      setError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      if (mounted.current && myTick === tick.current) {
        setLoading(false);
      }
    }
  }, []);

  const refresh = useCallback(() => {
    void run();
  }, [run]);

  useEffect(() => {
    mounted.current = true;
    if (!enabled) {
      setLoading(false);
      return () => {
        mounted.current = false;
      };
    }
    setLoading(true);
    void run();
    const id = setInterval(() => {
      void run();
    }, intervalMs);
    return () => {
      mounted.current = false;
      clearInterval(id);
    };
  }, [run, intervalMs, enabled]);

  return {
    data,
    error,
    loading,
    reconnecting: hasSucceeded.current && error !== null,
    refresh,
  };
}
