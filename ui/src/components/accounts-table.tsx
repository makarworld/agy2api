import { LogIn, Pencil } from 'lucide-react';
import { type PoolAccount } from '../hooks/use-stats';
import { useApiKey } from '../hooks/use-api-key';
import { apiUrl } from '../lib/api';

function formatPercent(val: number | null | undefined): string {
  if (val === null || val === undefined) return '—';
  return `${Math.round(val * 100)}%`;
}

function getQuotaColorClass(fraction: number | null | undefined): string {
  if (fraction === null || fraction === undefined) return 'bg-muted text-muted-foreground border-border';
  if (fraction > 0.5) return 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30';
  if (fraction > 0.2) return 'bg-amber-500/15 text-amber-400 border-amber-500/30';
  return 'bg-red-500/15 text-red-400 border-red-500/30';
}

function QuotaBadges({ quota }: { quota?: PoolAccount['quota'] }) {
  if (!quota) return null;

  const hasGemini = quota.gemini_5h !== undefined || quota.gemini_weekly !== undefined;
  const hasClaude = quota.claude_5h !== undefined || quota.claude_weekly !== undefined;

  if (!hasGemini && !hasClaude) return null;

  const g5hTitle = quota.gemini_5h_reset ? `Gemini 5h reset: ${new Date(quota.gemini_5h_reset).toLocaleTimeString()}` : 'Gemini 5h limit';
  const gWeeklyTitle = quota.gemini_weekly_reset ? `Gemini 7d reset: ${new Date(quota.gemini_weekly_reset).toLocaleDateString()}` : 'Gemini 7d limit';
  const c5hTitle = quota.claude_5h_reset ? `Claude 5h reset: ${new Date(quota.claude_5h_reset).toLocaleTimeString()}` : 'Claude 5h limit';
  const cWeeklyTitle = quota.claude_weekly_reset ? `Claude 7d reset: ${new Date(quota.claude_weekly_reset).toLocaleDateString()}` : 'Claude 7d limit';

  return (
    <div className="flex flex-wrap items-center gap-1.5 mt-1">
      {hasGemini && (
        <span
          className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono border ${getQuotaColorClass(
            quota.gemini_5h ?? quota.gemini_weekly
          )}`}
          title={`${g5hTitle} | ${gWeeklyTitle}`}
        >
          <span className="font-semibold text-[9px] uppercase tracking-wider opacity-75">Gemini</span>
          <span>5h: {formatPercent(quota.gemini_5h)}</span>
          <span className="opacity-40">/</span>
          <span>7d: {formatPercent(quota.gemini_weekly)}</span>
        </span>
      )}
      {hasClaude && (
        <span
          className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono border ${getQuotaColorClass(
            quota.claude_5h ?? quota.claude_weekly
          )}`}
          title={`${c5hTitle} | ${cWeeklyTitle}`}
        >
          <span className="font-semibold text-[9px] uppercase tracking-wider opacity-75">Claude</span>
          <span>5h: {formatPercent(quota.claude_5h)}</span>
          <span className="opacity-40">/</span>
          <span>7d: {formatPercent(quota.claude_weekly)}</span>
        </span>
      )}
    </div>
  );
}

export function AccountsTable({
  accounts,
  poolEnabled,
  onChanged,
  onRelogin,
}: {
  accounts: PoolAccount[];
  poolEnabled: boolean;
  onChanged: () => void;
  onRelogin?: (acc: PoolAccount) => void;
}) {
  const { apiKey } = useApiKey();

  const editProxy = async (acc: PoolAccount) => {
    const next = window.prompt(
      `Proxy for "${acc.label}" (e.g. http://user:pass@host:port). Leave empty to clear:`,
      acc.proxy || ''
    );
    if (next === null) return; // cancelled
    await fetch(apiUrl(`/v1/accounts/${acc.id}/proxy`), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${apiKey}` },
      body: JSON.stringify({ proxy: next.trim() || null }),
    });
    onChanged();
  };

  if (!poolEnabled) {
    return (
      <div className="border rounded-xl p-4 bg-card text-sm text-muted-foreground">
        Account pool not configured (AGY_POOL_ENABLED=false).
      </div>
    );
  }
  if (accounts.length === 0) {
    return (
      <div className="border rounded-xl p-4 bg-card text-sm text-muted-foreground">
        No accounts in pool yet. Use "Add Account" above, or run <code>scripts/add_account_to_pool.py</code>.
      </div>
    );
  }
  return (
    <div className="border rounded-xl bg-card overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-muted/50 text-muted-foreground">
          <tr>
            <th className="text-left p-3 font-medium">Label & Limits</th>
            <th className="text-left p-3 font-medium">Status</th>
            <th className="text-left p-3 font-medium">Proxy</th>
            <th className="text-left p-3 font-medium">Requests</th>
            <th className="text-left p-3 font-medium">Tokens IN/OUT</th>
            <th className="text-left p-3 font-medium">Last used</th>
            <th className="text-right p-3 font-medium">Actions</th>
          </tr>
        </thead>
        <tbody>
          {accounts.map((acc) => (
            <tr key={acc.id} className="border-t">
              <td className="p-3">
                <div className="font-medium text-foreground flex items-center flex-wrap gap-1.5">
                  <span>{acc.label || acc.id}</span>
                  {acc.email && (
                    <span className="text-xs font-mono text-muted-foreground">
                      ({acc.email})
                    </span>
                  )}
                  {acc.active && <span className="ml-1 text-xs text-emerald-500 font-normal">● active</span>}
                </div>
                <QuotaBadges quota={acc.quota} />
              </td>
              <td className="p-3">
                <span
                  className={`px-2 py-0.5 rounded-full text-xs ${
                    acc.status === 'healthy'
                      ? 'bg-emerald-500/20 text-emerald-400'
                      : acc.status === 'cooldown'
                      ? 'bg-amber-500/20 text-amber-400'
                      : 'bg-red-500/20 text-red-400'
                  }`}
                >
                  {acc.status}
                </span>
              </td>
              <td className="p-3">
                <button
                  onClick={() => editProxy(acc)}
                  className="flex items-center gap-1.5 text-muted-foreground hover:text-foreground transition-colors"
                  title="Edit proxy"
                >
                  <Pencil className="w-3 h-3" />
                  {acc.proxy ? (
                    <span className="font-mono text-xs">{acc.proxy}</span>
                  ) : (
                    <span className="text-xs italic">none</span>
                  )}
                </button>
              </td>
              <td className="p-3">{acc.total_requests}</td>
              <td className="p-3">
                {acc.total_prompt_tokens.toLocaleString()} / {acc.total_completion_tokens.toLocaleString()}
              </td>
              <td className="p-3 text-muted-foreground">
                {acc.last_used_ts ? new Date(acc.last_used_ts * 1000).toLocaleString() : '—'}
              </td>
              <td className="p-3 text-right">
                {onRelogin && (
                  <button
                    onClick={() => onRelogin(acc)}
                    className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-md bg-secondary hover:bg-secondary/80 text-secondary-foreground transition-colors"
                    title="Relogin and refresh OAuth tokens for this account"
                  >
                    <LogIn className="w-3 h-3" />
                    Relogin
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
