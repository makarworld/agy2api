import { RefreshCw, BarChart3 } from 'lucide-react';
import { Button } from '../components/ui/button';
import { useStats, type TimeseriesBucket } from '../hooks/use-stats';
import { AccountsTable } from '../components/accounts-table';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';

function formatBucketTime(unixSeconds: number) {
  const d = new Date(unixSeconds * 1000);
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit' });
}

function StatTile({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="border rounded-xl p-4 bg-card">
      <div className="text-xs text-muted-foreground uppercase tracking-wide">{label}</div>
      <div className="text-2xl font-semibold mt-1">{value}</div>
    </div>
  );
}

function formatUptime(seconds: number) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 24) return `${Math.floor(h / 24)}d ${h % 24}h`;
  return `${h}h ${m}m`;
}

function UptimeStrip({ events }: { events: { ts: number; event_type: 'down' | 'up' }[] }) {
  const now = Math.floor(Date.now() / 1000);
  const bucketSeconds = 3600;
  const bucketCount = 48;
  const sorted = [...events].sort((a, b) => a.ts - b.ts);

  const buckets = Array.from({ length: bucketCount }, (_, i) => {
    const bucketEnd = now - (bucketCount - 1 - i) * bucketSeconds;
    const bucketStart = bucketEnd - bucketSeconds;

    let state: 'up' | 'down' = 'up';
    for (const ev of sorted) {
      if (ev.ts <= bucketStart) state = ev.event_type;
    }
    let hadDown = state === 'down';
    for (const ev of sorted) {
      if (ev.ts > bucketStart && ev.ts <= bucketEnd && ev.event_type === 'down') hadDown = true;
    }
    return { bucketStart, status: hadDown ? 'down' : 'up' as const };
  });

  return (
    <div className="border rounded-xl p-4 bg-card">
      <div className="text-xs text-muted-foreground uppercase tracking-wide mb-2">
        Uptime — last 48h
      </div>
      <div className="flex gap-0.5">
        {buckets.map((b, i) => (
          <div
            key={i}
            title={new Date(b.bucketStart * 1000).toLocaleString()}
            className={`h-6 flex-1 rounded-sm ${b.status === 'up' ? 'bg-emerald-500/70' : 'bg-red-500/80'}`}
          />
        ))}
      </div>
    </div>
  );
}

export function StatsPage() {
  const { summary, timeseries, accounts, poolEnabled, loading, refresh } = useStats();

  const chartData: (TimeseriesBucket & { label: string; uncached_prompt_tokens: number })[] = timeseries.map((b) => ({
    ...b,
    label: formatBucketTime(b.bucket_start),
    uncached_prompt_tokens: Math.max(0, b.prompt_tokens - b.cache_tokens),
  }));

  return (
    <div className="flex flex-col flex-1 h-full p-8 overflow-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Stats</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Token usage, account pool health, and service uptime.
          </p>
        </div>
        <Button onClick={refresh} disabled={loading} variant="outline" size="sm" className="gap-2">
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      {!summary ? (
        <div className="text-muted-foreground text-sm">Loading stats…</div>
      ) : (
        <div className="space-y-6">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatTile label="Uptime" value={formatUptime(summary.uptime_seconds)} />
            <StatTile label="Requests" value={summary.totals.requests.toLocaleString()} />
            <StatTile label="Failed" value={summary.totals.failed.toLocaleString()} />
            <StatTile
              label="Tokens IN / OUT / CACHE"
              value={`${summary.totals.prompt_tokens.toLocaleString()} / ${summary.totals.completion_tokens.toLocaleString()} / ${summary.totals.cache_tokens.toLocaleString()}`}
            />
            <StatTile
              label="Total processed"
              value={(summary.totals.total_tokens ?? summary.totals.prompt_tokens + summary.totals.completion_tokens).toLocaleString()}
            />
          </div>

          <UptimeStrip events={summary.recent_downtime_events} />

          <div className="border rounded-xl p-4 bg-card">
            <div className="text-xs text-muted-foreground uppercase tracking-wide mb-2 flex items-center gap-2">
              <BarChart3 className="w-4 h-4" /> Token usage over time
            </div>
            <ResponsiveContainer width="100%" height={280}>
              <AreaChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
                <XAxis dataKey="label" fontSize={12} />
                <YAxis fontSize={12} />
                <Tooltip />
                <Legend />
                <Area type="monotone" dataKey="uncached_prompt_tokens" name="IN (new)" stackId="1" stroke="#60a5fa" fill="#60a5fa" fillOpacity={0.5} />
                <Area type="monotone" dataKey="cache_tokens" name="CACHE (subset of IN)" stackId="1" stroke="#fbbf24" fill="#fbbf24" fillOpacity={0.5} />
                <Area type="monotone" dataKey="completion_tokens" name="OUT" stackId="1" stroke="#34d399" fill="#34d399" fillOpacity={0.5} />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          <div>
            <div className="text-xs text-muted-foreground uppercase tracking-wide mb-2">Account pool</div>
            <AccountsTable accounts={accounts} poolEnabled={poolEnabled} onChanged={refresh} />
          </div>
        </div>
      )}
    </div>
  );
}
