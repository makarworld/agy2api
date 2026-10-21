import { useCallback, useEffect, useState } from 'react';
import { useApiKey } from './use-api-key';
import { apiUrl } from '../lib/api';

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
    total_tokens: number;
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

export interface AccountQuota {
  gemini_5h?: number | null;
  gemini_weekly?: number | null;
  claude_5h?: number | null;
  claude_weekly?: number | null;
  gemini_5h_reset?: string | null;
  gemini_weekly_reset?: string | null;
  claude_5h_reset?: string | null;
  claude_weekly_reset?: string | null;
}

export interface QuotaCycle {
  id: number;
  account_id: string;
  cycle_start_ts: number;
  cycle_end_ts?: number | null;
  initial_fraction: number;
  current_fraction: number;
  fraction_spent: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_requests: number;
  model_stats: Record<string, { requests: number; prompt_tokens: number; completion_tokens: number }>;
  is_active: number;
}

export interface PoolAccount {
  id: string;
  label: string;
  name?: string | null;
  picture?: string | null;
  email?: string | null;
  added_at: number;
  proxy: string | null;
  active: boolean;
  status: 'healthy' | 'cooldown' | 'unhealthy' | 'exhausted_429';
  cooldown_until: number | null;
  consecutive_failures: number;
  last_used_ts: number | null;
  total_requests: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  model_cooldowns?: Record<string, number>;
  quota?: AccountQuota;
  active_cycle?: QuotaCycle | null;
}

export function useStats(pollIntervalMs = 30000) {
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
        fetch(apiUrl('/v1/stats/summary'), { headers }),
        fetch(apiUrl('/v1/stats/timeseries?bucket_seconds=3600&window_hours=48'), { headers }),
        fetch(apiUrl('/v1/accounts'), { headers }),
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
    const handleAuthSuccess = () => refresh();
    window.addEventListener('agy:auth-success', handleAuthSuccess);
    return () => {
      clearInterval(interval);
      window.removeEventListener('agy:auth-success', handleAuthSuccess);
    };
  }, [refresh, pollIntervalMs]);

  return { summary, timeseries, accounts, poolEnabled, loading, error, refresh };
}
