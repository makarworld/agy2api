import { useState } from 'react';
import { LogIn, Pencil, AlertTriangle, X, RefreshCw } from 'lucide-react';
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

function ModelCooldownBadges({ cooldowns }: { cooldowns?: Record<string, number> }) {
  if (!cooldowns || Object.keys(cooldowns).length === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-1 mt-1">
      {Object.entries(cooldowns).map(([model, until]) => {
        const secLeft = Math.max(0, Math.round(until - Date.now() / 1000));
        if (secLeft <= 0) return null;
        return (
          <span
            key={model}
            className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono bg-red-500/15 text-red-400 border border-red-500/30"
            title={`Cooldown until ${new Date(until * 1000).toLocaleTimeString()}`}
          >
            <span className="font-semibold text-[9px] uppercase">{model.replace('gemini-', '').replace('claude-', '')}</span>
            <span>429 ({secLeft}s)</span>
          </span>
        );
      })}
    </div>
  );
}

interface AccountErrorItem {
  id: number;
  ts: number;
  endpoint: string;
  model: string;
  latency_ms: number;
  error_type: string;
  prompt_preview: string;
  response_preview: string;
}

function AccountErrorsModal({
  account,
  onClose,
}: {
  account: PoolAccount;
  onClose: () => void;
}) {
  const { apiKey } = useApiKey();
  const [errors, setErrors] = useState<AccountErrorItem[]>([]);
  const [loading, setLoading] = useState(true);

  useState(() => {
    fetch(apiUrl(`/v1/accounts/${account.id}/errors?limit=20`), {
      headers: { Authorization: `Bearer ${apiKey}` },
    })
      .then((r) => r.json())
      .then((d) => setErrors(d.errors || []))
      .catch(() => setErrors([]))
      .finally(() => setLoading(false));
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4">
      <div className="bg-card border rounded-xl shadow-xl w-full max-w-3xl max-h-[85vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95">
        <div className="flex items-center justify-between p-4 border-b">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-amber-400" />
            <div>
              <h3 className="font-semibold text-foreground text-sm">
                Recent Errors for "{account.label || account.id}"
              </h3>
              <p className="text-xs text-muted-foreground font-mono">{account.email || account.id}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-4 overflow-y-auto flex-1 space-y-3">
          {loading ? (
            <div className="flex items-center justify-center p-8 text-sm text-muted-foreground gap-2">
              <RefreshCw className="w-4 h-4 animate-spin" />
              Loading error history...
            </div>
          ) : errors.length === 0 ? (
            <div className="text-center p-8 text-sm text-muted-foreground">
              No recent errors recorded for this account.
            </div>
          ) : (
            errors.map((err) => (
              <div key={err.id} className="border border-destructive/30 bg-destructive/5 rounded-lg p-3 space-y-1.5 text-xs">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-destructive font-mono">#{err.id}</span>
                    <span className="font-semibold text-foreground">{err.error_type || 'Error'}</span>
                    <span className="px-1.5 py-0.5 rounded bg-muted font-mono text-[10px] text-muted-foreground">
                      {err.model}
                    </span>
                    <span className="text-[10px] text-muted-foreground">
                      {err.latency_ms}ms
                    </span>
                  </div>
                  <span className="text-muted-foreground text-[11px]">
                    {new Date(err.ts * 1000).toLocaleString()}
                  </span>
                </div>
                {err.response_preview && (
                  <div className="bg-background/80 border rounded p-2 font-mono text-[11px] text-foreground whitespace-pre-wrap break-all">
                    {err.response_preview}
                  </div>
                )}
                {err.prompt_preview && (
                  <div className="text-[11px] text-muted-foreground italic truncate" title={err.prompt_preview}>
                    Prompt: {err.prompt_preview}
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </div>
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
  const [selectedErrorAcc, setSelectedErrorAcc] = useState<PoolAccount | null>(null);
  const [checkingHealthId, setCheckingHealthId] = useState<string | null>(null);
  const [healthMsg, setHealthMsg] = useState<{ id: string; text: string; ok: boolean } | null>(null);

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

  const runHealthCheck = async (acc: PoolAccount) => {
    setCheckingHealthId(acc.id);
    setHealthMsg(null);
    try {
      const res = await fetch(apiUrl(`/v1/accounts/${acc.id}/healthcheck`), {
        method: 'POST',
        headers: { Authorization: `Bearer ${apiKey}` },
      });
      const data = await res.json();
      setHealthMsg({
        id: acc.id,
        text: data.message || (data.recovered ? 'Account restored to healthy!' : 'Still rate-limited'),
        ok: !!data.recovered,
      });
      onChanged();
    } catch (e: any) {
      setHealthMsg({ id: acc.id, text: e.message || 'Check failed', ok: false });
    } finally {
      setCheckingHealthId(null);
    }
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
    <>
      {selectedErrorAcc && (
        <AccountErrorsModal
          account={selectedErrorAcc}
          onClose={() => setSelectedErrorAcc(null)}
        />
      )}
      <div className="border rounded-xl bg-card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-muted/50 text-muted-foreground">
            <tr>
              <th className="text-left p-3 font-medium">Label & Limits</th>
              <th className="text-left p-3 font-medium">Status & Cooldown</th>
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
                  <div className="flex flex-col gap-1 items-start">
                    <div className="flex items-center gap-1.5">
                      <span
                        className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                          acc.status === 'healthy'
                            ? 'bg-emerald-500/20 text-emerald-400'
                            : acc.status === 'cooldown'
                            ? 'bg-amber-500/20 text-amber-400'
                            : 'bg-red-500/20 text-red-400'
                        }`}
                      >
                        {acc.status}
                      </span>
                      {acc.status !== 'healthy' && (
                        <button
                          onClick={() => runHealthCheck(acc)}
                          disabled={checkingHealthId === acc.id}
                          className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[11px] font-medium rounded bg-secondary hover:bg-secondary/80 text-foreground transition-colors"
                          title="Check with Google if quota has recovered and reset cooldown"
                        >
                          <RefreshCw className={`w-3 h-3 ${checkingHealthId === acc.id ? 'animate-spin' : ''}`} />
                          Check
                        </button>
                      )}
                    </div>
                    {acc.cooldown_until && acc.cooldown_until > Date.now() / 1000 && (
                      <span className="text-[10px] text-muted-foreground font-mono">
                        until {new Date(acc.cooldown_until * 1000).toLocaleTimeString()}
                      </span>
                    )}
                    {healthMsg && healthMsg.id === acc.id && (
                      <span className={`text-[10px] ${healthMsg.ok ? 'text-emerald-400' : 'text-amber-400'}`}>
                        {healthMsg.text}
                      </span>
                    )}
                    <ModelCooldownBadges cooldowns={acc.model_cooldowns} />
                  </div>
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
                  <div className="inline-flex items-center gap-1.5">
                    <button
                      onClick={() => setSelectedErrorAcc(acc)}
                      className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium rounded-md bg-secondary hover:bg-secondary/80 text-secondary-foreground transition-colors"
                      title="View recent error logs for this account"
                    >
                      <AlertTriangle className="w-3 h-3 text-amber-400" />
                      Errors
                    </button>
                    {onRelogin && (
                      <button
                        onClick={() => onRelogin(acc)}
                        className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-md bg-primary hover:bg-primary/90 text-primary-foreground transition-colors"
                        title="Relogin and refresh OAuth tokens for this account"
                      >
                        <LogIn className="w-3 h-3" />
                        Relogin
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

