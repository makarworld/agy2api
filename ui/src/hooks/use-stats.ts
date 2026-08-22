import { useCallback, useEffect, useState } from 'react';
import { useApiKey } from './use-api-key';

export interface StatsSummary {
  uptime_seconds: number;
  app_start_ts: number;
  totals: {
    requests: number;
    success: number;
    failed: number;
    prompt_tokens: number;
    completion_tokens: number;
    cache_tokens: number;
  };
  by_model: { model: string; requests: number; prompt_tokens: number; completion_tokens: number; cache_tokens: number }[];
  by_account: { pool_account: string; requests: number; prompt_tokens: number; completion_tokens: number }[];
  recent_downtime_events: { ts: number; event_type: 'down' | 'up'; reason: string | null }[];
}

export interface TimeseriesBucket {
  bucket_start: number;
  requests: number;
  prompt_tokens: number;
  completion_tokens: number;
  cache_tokens: number;
  failures: number;
}

export interface PoolAccount {
  id: string;
  label: string;
  added_at: number;
  proxy: string | null;
  active: boolean;
  status: 'healthy' | 'cooldown' | 'unhealthy';
  cooldown_until: number | null;
  consecutive_failures: number;
  last_used_ts: number | null;
  total_requests: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
}

export function useStats(pollIntervalMs = 15000) {
  const { apiKey } = useApiKey();
  const [summary, setSummary] = useState<StatsSummary | null>(null);
  const [timeseries, setTimeseries] = useState<TimeseriesBucket[]>([]);
  const [accounts, setAccounts] = useState<PoolAccount[]>([]);
  const [poolEnabled, setPoolEnabled] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!apiKey) return;
    setLoading(true);
    setError(null);
    try {
      const headers = { Authorization: `Bearer ${apiKey}` };
      const [summaryRes, tsRes, accountsRes] = await Promise.all([
        fetch('/v1/stats/summary', { headers }),
        fetch('/v1/stats/timeseries?bucket_seconds=3600&window_hours=48', { headers }),
        fetch('/v1/accounts', { headers }),
      ]);

      if (summaryRes.ok) setSummary(await summaryRes.json());
      if (tsRes.ok) {
        const data = await tsRes.json();
        setTimeseries(data.data || []);
      }
      if (accountsRes.ok) {
        const data = await accountsRes.json();
        setPoolEnabled(!!data.pool_enabled);
        setAccounts(data.accounts || []);
      }
    } catch (err: any) {
      setError(err.message);
    }
    setLoading(false);
  }, [apiKey]);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, pollIntervalMs);
    return () => clearInterval(interval);
  }, [refresh, pollIntervalMs]);

  return { summary, timeseries, accounts, poolEnabled, loading, error, refresh };
}
