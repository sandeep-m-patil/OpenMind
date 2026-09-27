import { useCallback, useEffect, useRef, useState } from "react";

export interface Polled<T> {
  data: T | null;
  error: string | null;
  reload: () => void;
}

/** Fetch now, then every `intervalMs` while `shouldPoll(data)` is true. */
export function usePolling<T>(load: () => Promise<T>, intervalMs: number, shouldPoll: (data: T | null) => boolean = () => true): Polled<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const loadRef = useRef(load);
  loadRef.current = load;

  const reload = useCallback(() => {
    loadRef
      .current()
      .then((value) => {
        setData(value);
        setError(null);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  useEffect(reload, [reload]);

  const isPolling = shouldPoll(data);
  useEffect(() => {
    if (!isPolling) return undefined;
    const timer = setInterval(reload, intervalMs);
    return () => clearInterval(timer);
  }, [isPolling, intervalMs, reload]);

  return { data, error, reload };
}
