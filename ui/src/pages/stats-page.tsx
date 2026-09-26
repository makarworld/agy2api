import React from 'react';
import { RefreshCw, BarChart3, Clock, Zap, ArrowDownRight, ArrowUpRight, Activity } from 'lucide-react';
import { Button } from '../components/ui/button';
import { useStats, type TimeseriesBucket } from '../hooks/use-stats';
import { AccountsTable } from '../components/accounts-table';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';

function formatTokens(n: number | null | undefined): string {
  if (!n) return '0';
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(2)}B`;
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return n.toLocaleString();
}

function formatBucketTime(unixSeconds: number) {
  const d = new Date(unixSeconds * 1000);
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit' });
}

function formatUptime(seconds: number) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 24) return `${Math.floor(h / 24)}d ${h % 24}h`;
  return `${h}h ${m}m`;
}

interface StatCardProps {
  label: string;
  value: string;
  subValue?: string;
  icon: React.ReactNode;
  badge?: React.ReactNode;
  tooltip?: string;
}

function StatCard({ label, value, subValue, icon, badge, tooltip }: StatCardProps) {
  return (
    <div
      className="border border-border/80 rounded-xl p-4 bg-card shadow-xs flex flex-col justify-between hover:border-border transition-colors"
      title={tooltip}
    >
      <div className="flex items-center justify-between">
        <span className="text-[11px] text-muted-foreground uppercase tracking-wider font-medium flex items-center gap-1.5">
          {icon}
          {label}
        </span>
        {badge}
      </div>
      <div className="mt-2.5">
        <div className="text-2xl font-bold font-mono tracking-tight text-foreground">{value}</div>
        {subValue && (
          <div className="text-xs text-muted-foreground mt-0.5 font-sans truncate">{subValue}</div>
        )}
      </div>
    </div>
  );
}

function UptimeStrip({ events }: { events: { ts: number; event_type: 'down' | 'up' }[] }) {
  const now = Math.floor(Date.now() / 1000);
  const bucketSeconds = 3600;
  const bucketCount = 48;
  const sorted = [...events].sort((a, b) => a.ts - b.ts);

  let downCount = 0;
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
    if (hadDown) downCount++;
    return { bucketStart, status: hadDown ? ('down' as const) : ('up' as const) };
  });

  const uptimePct = (((bucketCount - downCount) / bucketCount) * 100).toFixed(1);

  return (
    <div className="border border-border/80 rounded-xl p-4 bg-card shadow-xs space-y-3">
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted-foreground uppercase tracking-wider font-medium flex items-center gap-1.5 text-[11px]">
          <Activity className="w-3.5 h-3.5 text-emerald-400" />
          Доступность сервиса (последние 48 часов)
        </span>
        <span className="font-mono text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded-md text-[11px] font-medium">
          {uptimePct}% доступность
        </span>
      </div>

      <div className="flex items-center gap-[3px]">
        {buckets.map((b, i) => (
          <div
            key={i}
            title={`${new Date(b.bucketStart * 1000).toLocaleString()} — ${
              b.status === 'up' ? 'Работает без сбоев' : 'Был сбой'
            }`}
            className={`h-6 flex-1 rounded-[2px] cursor-pointer transition-opacity hover:opacity-100 ${
              b.status === 'up' ? 'bg-emerald-500/75 hover:bg-emerald-400' : 'bg-rose-500 hover:bg-rose-400'
            }`}
          />
        ))}
      </div>

      <div className="flex items-center justify-between text-[11px] text-muted-foreground/70 font-mono">
        <span>48 часов назад</span>
        <span className="text-muted-foreground/40 font-sans text-[10px]">1 сегмент = 1 час</span>
        <span>Сейчас</span>
      </div>
    </div>
  );
}

function CustomChartTooltip({ active, payload, label }: any) {
  if (!active || !payload || !payload.length) return null;

  return (
    <div className="bg-popover/95 border border-border/80 rounded-xl p-3 shadow-xl text-xs font-mono space-y-1.5 backdrop-blur-md">
      <div className="font-sans font-semibold text-foreground border-b border-border/60 pb-1">{label}</div>
      {payload.map((entry: any, i: number) => (
        <div key={i} className="flex items-center justify-between gap-4">
          <span className="flex items-center gap-1.5 text-muted-foreground">
            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: entry.color }} />
            {entry.name}:
          </span>
          <span className="font-semibold text-foreground">{formatTokens(entry.value)}</span>
        </div>
      ))}
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

  const totals = summary?.totals;
  const successRate = totals && totals.requests > 0
    ? (((totals.requests - totals.failed) / totals.requests) * 100).toFixed(1)
    : '100';

  return (
    <div className="flex-1 p-6 md:p-8 overflow-auto">
      <div className="max-w-7xl mx-auto w-full space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Stats</h1>
            <p className="text-sm text-muted-foreground mt-1">
              Token usage, account pool health, and service uptime.
            </p>
          </div>
          <Button onClick={refresh} disabled={loading} variant="outline" size="sm" className="gap-2 cursor-pointer">
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </div>

        {!summary ? (
          <div className="text-muted-foreground text-sm py-8 text-center">Loading stats…</div>
        ) : (
          <div className="space-y-6">
            {/* 4 Balanced Metric Cards */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              <StatCard
                label="Аптайм"
                value={formatUptime(summary.uptime_seconds)}
                subValue="Сервис работает штатно"
                icon={<Clock className="w-3.5 h-3.5 text-primary" />}
                badge={
                  <span className="inline-flex items-center gap-1 text-[10px] font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-1.5 py-0.2 rounded-md">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                    Онлайн
                  </span>
                }
              />
              <StatCard
                label="Запросы"
                value={summary.totals.requests.toLocaleString()}
                subValue={`${successRate}% успешно · ${summary.totals.failed} ошибок`}
                icon={<Zap className="w-3.5 h-3.5 text-amber-400" />}
              />
              <StatCard
                label="Входные токены"
                value={formatTokens(summary.totals.prompt_tokens)}
                subValue={`Кэш: ${formatTokens(summary.totals.cache_tokens)} (${
                  summary.totals.prompt_tokens > 0
                    ? Math.round((summary.totals.cache_tokens / summary.totals.prompt_tokens) * 100)
                    : 0
                }%)`}
                icon={<ArrowDownRight className="w-3.5 h-3.5 text-sky-400" />}
                tooltip={`Всего на входе: ${summary.totals.prompt_tokens.toLocaleString()} | Из кэша: ${summary.totals.cache_tokens.toLocaleString()}`}
              />
              <StatCard
                label="Выходные токены"
                value={formatTokens(summary.totals.completion_tokens)}
                subValue={`Всего обработано: ${formatTokens(
                  summary.totals.total_tokens ?? (summary.totals.prompt_tokens + summary.totals.completion_tokens)
                )}`}
                icon={<ArrowUpRight className="w-3.5 h-3.5 text-emerald-400" />}
                tooltip={`Выход: ${summary.totals.completion_tokens.toLocaleString()} токенов`}
              />
            </div>

            {/* Uptime Strip */}
            <UptimeStrip events={summary.recent_downtime_events} />

            {/* Token Usage Chart */}
            <div className="border border-border/80 rounded-xl p-5 bg-card shadow-xs space-y-4">
              <div className="flex items-center justify-between">
                <div className="text-xs text-muted-foreground uppercase tracking-wide font-medium flex items-center gap-2">
                  <BarChart3 className="w-4 h-4 text-primary" /> Распределение токенов по времени
                </div>
                <div className="flex items-center gap-4 text-xs font-mono">
                  <span className="flex items-center gap-1.5 text-sky-400">
                    <span className="w-2 h-2 rounded-full bg-sky-400" />
                    Новые (IN)
                  </span>
                  <span className="flex items-center gap-1.5 text-indigo-400">
                    <span className="w-2 h-2 rounded-full bg-indigo-400" />
                    Кэш (IN)
                  </span>
                  <span className="flex items-center gap-1.5 text-emerald-400">
                    <span className="w-2 h-2 rounded-full bg-emerald-400" />
                    Выход (OUT)
                  </span>
                </div>
              </div>

              <div className="h-[300px] w-full pt-2">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                    <defs>
                      <linearGradient id="gradIn" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#38bdf8" stopOpacity={0.4} />
                        <stop offset="95%" stopColor="#38bdf8" stopOpacity={0.0} />
                      </linearGradient>
                      <linearGradient id="gradCache" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#818cf8" stopOpacity={0.4} />
                        <stop offset="95%" stopColor="#818cf8" stopOpacity={0.0} />
                      </linearGradient>
                      <linearGradient id="gradOut" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#34d399" stopOpacity={0.4} />
                        <stop offset="95%" stopColor="#34d399" stopOpacity={0.0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#27272a" opacity={0.6} />
                    <XAxis
                      dataKey="label"
                      tick={{ fill: '#71717a', fontSize: 11 }}
                      axisLine={{ stroke: '#27272a' }}
                      tickLine={{ stroke: '#27272a' }}
                    />
                    <YAxis
                      tick={{ fill: '#71717a', fontSize: 11 }}
                      tickFormatter={(v) => formatTokens(v)}
                      axisLine={{ stroke: '#27272a' }}
                      tickLine={{ stroke: '#27272a' }}
                      width={60}
                    />
                    <Tooltip content={<CustomChartTooltip />} />
                    <Area
                      type="monotone"
                      dataKey="uncached_prompt_tokens"
                      name="Новые (IN)"
                      stackId="1"
                      stroke="#38bdf8"
                      strokeWidth={1.5}
                      fill="url(#gradIn)"
                    />
                    <Area
                      type="monotone"
                      dataKey="cache_tokens"
                      name="Кэш (IN)"
                      stackId="1"
                      stroke="#818cf8"
                      strokeWidth={1.5}
                      fill="url(#gradCache)"
                    />
                    <Area
                      type="monotone"
                      dataKey="completion_tokens"
                      name="Выход (OUT)"
                      stackId="1"
                      stroke="#34d399"
                      strokeWidth={1.5}
                      fill="url(#gradOut)"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Account Pool Section */}
            <div className="space-y-3">
              <div className="text-xs text-muted-foreground uppercase tracking-wider font-medium">
                Пул аккаунтов
              </div>
              <AccountsTable accounts={accounts} poolEnabled={poolEnabled} onChanged={refresh} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
