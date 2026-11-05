import { useCallback, useEffect, useState } from 'react';
import { errText } from './supabase';

// Minimal data loader: runs fn on mount and when deps change; reload() re-runs it.
export function useLoad<T>(fn: () => Promise<T>, deps: any[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const run = useCallback(async () => {
    setLoading(true);
    try { setData(await fn()); setError(null); } catch (e) { setError(errText(e)); }
    setLoading(false);
  }, deps); // eslint-disable-line
  useEffect(() => { run(); }, [run]);
  return { data, error, loading, reload: run };
}

// Throw on Supabase errors so useLoad can show them.
export async function q(p: PromiseLike<any>): Promise<any> {
  const { data, error } = await p;
  if (error) throw error;
  return data;
}
