import { useState } from 'react';
import { LogIn, Pencil, AlertTriangle, X, RefreshCw, CheckCircle2, Trash2, Check } from 'lucide-react';
import { type PoolAccount } from '../hooks/use-stats';
import { useApiKey } from '../hooks/use-api-key';
import { apiUrl } from '../lib/api';
import { Button } from './ui/button';

function formatTokens(n: number): string {
  if (!n) return '0';
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return n.toLocaleString();
}

function formatRelativeTime(unixSeconds: number | null | undefined): string {
  if (!unixSeconds) return '—';
  const sec = Number(unixSeconds);
  if (isNaN(sec) || sec <= 0) return '—';
  const diff = Math.max(0, Math.floor(Date.now() / 1000 - sec));
  if (diff < 5) return 'только что';
  if (diff < 60) return `${diff} с назад`;
  if (diff < 3600) return `${Math.floor(diff / 60)} мин назад`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} ч назад`;
  return `${Math.floor(diff / 86400)} д назад`;
}

function formatPercent(val: number | null | undefined): string {
  if (val === null || val === undefined) return '—';
  return `${Math.round(val * 100)}%`;
}

function QuotaItem({
  label,
  value5h,
  valueWeekly,
  title,
}: {
  label: string;
  value5h?: number | null;
  valueWeekly?: number | null;
  title: string;
}) {
  if (value5h === undefined && valueWeekly === undefined) return null;

  const minVal = Math.min(value5h ?? 1, valueWeekly ?? 1);
  const dotColor = minVal > 0.5 ? 'bg-emerald-400' : minVal > 0.2 ? 'bg-amber-400' : 'bg-red-400';
  const valColor = minVal > 0.5 ? 'text-emerald-400' : minVal > 0.2 ? 'text-amber-400' : 'text-red-400';

  return (
    <span
      className="inline-flex items-center gap-1.5 px-1.5 py-0.5 rounded text-[10px] font-mono bg-muted/50 border border-border/70 select-none shadow-2xs hover:bg-muted transition-colors whitespace-nowrap"
      title={title}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${dotColor} shrink-0`} />
      <span className="font-semibold text-foreground/85 font-sans tracking-tight text-[11px]">{label}</span>
      <span className="text-muted-foreground/60 text-[10px]">5h:</span>
      <span className={valColor}>{formatPercent(value5h)}</span>
      <span className="text-muted-foreground/30 font-sans">/</span>
      <span className="text-muted-foreground/60 text-[10px]">7d:</span>
      <span className={valColor}>{formatPercent(valueWeekly)}</span>
    </span>
  );
}

function QuotaBadges({ quota }: { quota?: PoolAccount['quota'] }) {
  if (!quota) return <span className="text-xs text-muted-foreground/40 font-mono">—</span>;

  const hasGemini = quota.gemini_5h !== undefined || quota.gemini_weekly !== undefined;
  const hasClaude = quota.claude_5h !== undefined || quota.claude_weekly !== undefined;

  if (!hasGemini && !hasClaude) return <span className="text-xs text-muted-foreground/40 font-mono">—</span>;

  const g5hTitle = quota.gemini_5h_reset ? `Gemini 5h reset: ${new Date(quota.gemini_5h_reset).toLocaleTimeString()}` : 'Gemini 5h limit';
  const gWeeklyTitle = quota.gemini_weekly_reset ? `Gemini 7d reset: ${new Date(quota.gemini_weekly_reset).toLocaleDateString()}` : 'Gemini 7d limit';
  const c5hTitle = quota.claude_5h_reset ? `Claude 5h reset: ${new Date(quota.claude_5h_reset).toLocaleTimeString()}` : 'Claude 5h limit';
  const cWeeklyTitle = quota.claude_weekly_reset ? `Claude 7d reset: ${new Date(quota.claude_weekly_reset).toLocaleDateString()}` : 'Claude 7d limit';

  return (
    <div className="flex flex-col gap-1 min-w-[160px]">
      {hasGemini && (
        <QuotaItem
          label="Gemini"
          value5h={quota.gemini_5h}
          valueWeekly={quota.gemini_weekly}
          title={`${g5hTitle} | ${gWeeklyTitle}`}
        />
      )}
      {hasClaude && (
        <QuotaItem
          label="Claude"
          value5h={quota.claude_5h}
          valueWeekly={quota.claude_weekly}
          title={`${c5hTitle} | ${cWeeklyTitle}`}
        />
      )}
    </div>
  );
}

function ModelCooldownBadges({ cooldowns }: { cooldowns?: Record<string, number> }) {
  if (!cooldowns || Object.keys(cooldowns).length === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-1 mt-0.5">
      {Object.entries(cooldowns).map(([model, until]) => {
        const secLeft = Math.max(0, Math.round(until - Date.now() / 1000));
        if (secLeft <= 0) return null;
        return (
          <span
            key={model}
            className="inline-flex items-center gap-1 px-1.5 py-0.2 rounded text-[10px] font-mono bg-red-500/10 text-red-400 border border-red-500/20"
            title={`Кулдаун до ${new Date(until * 1000).toLocaleTimeString()}`}
          >
            <span className="font-semibold text-[9px] uppercase tracking-wider">{model.replace('gemini-', '').replace('claude-', '')}</span>
            <span>429 ({secLeft}с)</span>
          </span>
        );
      })}
    </div>
  );
}

function AccountAvatar({
  name,
  email,
  picture,
  isActive,
}: {
  name?: string | null;
  email?: string | null;
  picture?: string | null;
  isActive?: boolean;
}) {
  const [imgError, setImgError] = useState(false);
  const initial = (name || email || '?')[0].toUpperCase();
  const ringClass = isActive
    ? 'ring-2 ring-emerald-500/80 ring-offset-1 ring-offset-background'
    : 'border border-border/80';

  if (picture && !imgError) {
    return (
      <div className="relative shrink-0">
        <img
          src={picture}
          alt=""
          onError={() => setImgError(true)}
          className={`w-7 h-7 rounded-full object-cover ${ringClass} shadow-xs`}
        />
        {isActive && (
          <span className="absolute -bottom-0.5 -right-0.5 w-2 h-2 rounded-full bg-emerald-500 border border-background" />
        )}
      </div>
    );
  }

  return (
    <div className="relative shrink-0">
      <div className={`w-7 h-7 rounded-full bg-primary/10 text-primary ${ringClass} flex items-center justify-center text-xs font-bold select-none shadow-xs`}>
        {initial}
      </div>
      {isActive && (
        <span className="absolute -bottom-0.5 -right-0.5 w-2 h-2 rounded-full bg-emerald-500 border border-background" />
      )}
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
      <div className="bg-card border border-border rounded-xl w-full max-w-2xl max-h-[80vh] flex flex-col shadow-2xl">
        <div className="flex items-center justify-between p-4 border-b border-border">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-400" />
            <span className="font-semibold text-sm">
              Recent Errors: {account.label} {account.email && `(${account.email})`}
            </span>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="overflow-y-auto p-4 flex-1 space-y-3">
          {loading ? (
            <div className="text-xs text-muted-foreground text-center py-6">Loading errors...</div>
          ) : errors.length === 0 ? (
            <div className="text-xs text-muted-foreground text-center py-6">
              No recent errors recorded for this account.
            </div>
          ) : (
            errors.map((err) => (
              <div key={err.id} className="border border-border/80 rounded-lg p-3 text-xs bg-muted/20 space-y-1.5">
                <div className="flex items-center justify-between text-[11px] text-muted-foreground font-mono">
                  <span>{new Date(err.ts * 1000).toLocaleString()}</span>
                  <span className="px-1.5 py-0.5 rounded bg-red-500/15 text-red-400 font-semibold border border-red-500/30">
                    {err.error_type}
                  </span>
                </div>
                <div className="text-muted-foreground font-mono text-[11px]">
                  endpoint: <span className="text-foreground">{err.endpoint}</span> | model:{' '}
                  <span className="text-foreground">{err.model}</span> | latency:{' '}
                  <span className="text-foreground">{err.latency_ms}ms</span>
                </div>
                {err.prompt_preview && (
                  <div className="text-muted-foreground font-mono text-[11px] truncate" title={err.prompt_preview}>
                    prompt: {err.prompt_preview}
                  </div>
                )}
                {err.response_preview && (
                  <div className="p-2 rounded bg-background border border-border/60 text-destructive font-mono text-[11px] whitespace-pre-wrap break-all max-h-32 overflow-y-auto">
                    {err.response_preview}
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
  const [refreshingQuotaId, setRefreshingQuotaId] = useState<string | null>(null);
  const [checkingHealthId, setCheckingHealthId] = useState<string | null>(null);
  const [activatingId, setActivatingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [healthMsg, setHealthMsg] = useState<{ id: string; text: string; ok: boolean } | null>(null);

  const handleActivate = async (acc: PoolAccount) => {
    setActivatingId(acc.id);
    try {
      await fetch(apiUrl(`/v1/accounts/${acc.id}/activate`), {
        method: 'POST',
        headers: { Authorization: `Bearer ${apiKey}` },
      });
      onChanged();
    } catch {
      // ignore
    } finally {
      setActivatingId(null);
    }
  };

  const refreshAccountQuota = async (acc: PoolAccount) => {
    setRefreshingQuotaId(acc.id);
    try {
      await fetch(apiUrl(`/v1/accounts/${acc.id}/refresh-quota`), {
        method: 'POST',
        headers: { Authorization: `Bearer ${apiKey}` },
      });
      onChanged();
    } catch {
      // ignore
    } finally {
      setRefreshingQuotaId(null);
    }
  };

  const editProxy = async (acc: PoolAccount) => {
    const next = window.prompt(
      `Прокси для "${acc.label}" (например, http://user:pass@host:port). Оставьте пустым, чтобы очистить:`,
      acc.proxy || ''
    );
    if (next === null) return;
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
        text: data.message || (data.recovered ? 'Аккаунт восстановлен!' : 'Лимит ещё активен'),
        ok: !!data.recovered,
      });
      onChanged();
    } catch (e: any) {
      setHealthMsg({ id: acc.id, text: e.message || 'Ошибка проверки', ok: false });
    } finally {
      setCheckingHealthId(null);
    }
  };

  const handleDelete = async (acc: PoolAccount) => {
    const displayName = acc.name || (acc.label && acc.label !== acc.email ? acc.label : acc.email || acc.id);
    if (!window.confirm(`Удалить аккаунт "${displayName}" из пула?`)) return;
    setDeletingId(acc.id);
    try {
      const res = await fetch(apiUrl(`/v1/accounts/${acc.id}`), {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${apiKey}` },
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Не удалось удалить аккаунт');
      }
      onChanged();
    } catch (e: any) {
      alert(e.message || 'Ошибка удаления');
    } finally {
      setDeletingId(null);
    }
  };

  if (!poolEnabled) {
    return (
      <div className="border border-border/80 rounded-xl p-4 bg-card text-sm text-muted-foreground">
        Account pool not configured (AGY_POOL_ENABLED=false).
      </div>
    );
  }
  if (accounts.length === 0) {
    return (
      <div className="border border-border/80 rounded-xl p-4 bg-card text-sm text-muted-foreground">
        В пуле пока нет аккаунтов. Нажмите «Добавить аккаунт» выше для подключения.
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
      <div className="border border-border/80 rounded-xl bg-card shadow-xs">
        <table className="w-full text-sm">
          <thead className="bg-muted/40 text-muted-foreground border-b border-border/80 text-[11px] font-medium uppercase tracking-wider">
            <tr>
              <th className="text-left py-2.5 px-3 whitespace-nowrap">Аккаунт</th>
              <th className="text-left py-2.5 px-3 whitespace-nowrap">Квоты</th>
              <th className="text-left py-2.5 px-2.5 whitespace-nowrap">Статус</th>
              <th className="text-left py-2.5 px-2.5 whitespace-nowrap">Прокси</th>
              <th className="text-right py-2.5 px-2.5 whitespace-nowrap">Запросы</th>
              <th className="text-right py-2.5 px-2.5 whitespace-nowrap">Токены</th>
              <th className="text-right py-2.5 px-2.5 whitespace-nowrap">Активность</th>
              <th className="text-right py-2.5 px-3 whitespace-nowrap">Действия</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/60">
            {accounts.map((acc) => (
              <tr key={acc.id} className="hover:bg-muted/20 transition-colors">
                {/* 1. Account */}
                <td className="py-2.5 px-3 align-middle">
                  <div className="flex items-center gap-2.5">
                    <AccountAvatar
                      name={acc.name}
                      email={acc.email}
                      picture={acc.picture}
                      isActive={acc.active}
                    />
                    <div className="flex flex-col min-w-0">
                      <span className="font-semibold text-foreground text-sm leading-tight whitespace-nowrap">
                        {acc.name || acc.label || acc.email || acc.id}
                      </span>
                      {acc.email && (acc.name || (acc.label && acc.label !== acc.email)) ? (
                        <span className="text-xs text-muted-foreground font-mono leading-tight mt-0.5 whitespace-nowrap">
                          {acc.email}
                        </span>
                      ) : null}
                    </div>
                  </div>
                </td>

                {/* 2. Quotas */}
                <td className="py-2.5 px-3 align-middle whitespace-nowrap">
                  <div className="flex items-center gap-1.5">
                    <QuotaBadges quota={acc.quota} />
                    <button
                      onClick={() => refreshAccountQuota(acc)}
                      disabled={refreshingQuotaId === acc.id}
                      className="p-1 rounded-md text-muted-foreground/60 hover:text-foreground hover:bg-muted/70 transition-colors disabled:opacity-50 cursor-pointer shrink-0"
                      title="Обновить квоты в Google"
                    >
                      <RefreshCw className={`w-3.5 h-3.5 ${refreshingQuotaId === acc.id ? 'animate-spin text-primary' : ''}`} />
                    </button>
                  </div>
                </td>

                {/* 3. Status */}
                <td className="py-2.5 px-2.5 align-middle text-left whitespace-nowrap">
                  <div className="flex flex-col gap-1 items-start">
                    <div className="flex items-center gap-1.5">
                      {acc.status === 'healthy' ? (
                        <span className="inline-flex items-center gap-1.5 text-xs text-emerald-400 font-medium bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded-md select-none whitespace-nowrap">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                          В норме
                        </span>
                      ) : acc.status === 'cooldown' ? (
                        <span className="inline-flex items-center gap-1.5 text-xs text-amber-400 font-medium bg-amber-500/10 border border-amber-500/20 px-2 py-0.5 rounded-md select-none whitespace-nowrap">
                          <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
                          Кулдаун
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1.5 text-xs text-red-400 font-medium bg-red-500/10 border border-red-500/20 px-2 py-0.5 rounded-md select-none whitespace-nowrap">
                          <span className="w-1.5 h-1.5 rounded-full bg-red-400" />
                          Ошибка
                        </span>
                      )}
                      {acc.status !== 'healthy' && (
                        <button
                          onClick={() => runHealthCheck(acc)}
                          disabled={checkingHealthId === acc.id}
                          className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer"
                          title="Проверить восстановление аккаунта в Google"
                        >
                          <RefreshCw className={`w-3 h-3 ${checkingHealthId === acc.id ? 'animate-spin text-primary' : ''}`} />
                        </button>
                      )}
                    </div>
                    {acc.cooldown_until && acc.cooldown_until > Date.now() / 1000 && (
                      <span className="text-[10px] text-muted-foreground font-mono whitespace-nowrap">
                        до {new Date(acc.cooldown_until * 1000).toLocaleTimeString()}
                      </span>
                    )}
                    {healthMsg && healthMsg.id === acc.id && (
                      <span className={`text-[10px] whitespace-nowrap ${healthMsg.ok ? 'text-emerald-400' : 'text-amber-400'}`}>
                        {healthMsg.text}
                      </span>
                    )}
                    <ModelCooldownBadges cooldowns={acc.model_cooldowns} />
                  </div>
                </td>

                {/* 4. Proxy */}
                <td className="py-2.5 px-2.5 align-middle text-left whitespace-nowrap">
                  <button
                    onClick={() => editProxy(acc)}
                    className="group inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs hover:bg-muted/60 transition-colors text-left cursor-pointer border border-transparent hover:border-border/60"
                    title="Нажмите, чтобы изменить прокси"
                  >
                    {acc.proxy ? (
                      <span className="font-mono text-xs text-foreground/90 bg-muted/60 px-1 py-0.5 rounded border border-border/50 max-w-[120px] truncate">
                        {acc.proxy}
                      </span>
                    ) : (
                      <span className="text-muted-foreground/40 text-xs font-mono">—</span>
                    )}
                    <Pencil className="w-3 h-3 text-muted-foreground/40 group-hover:text-foreground transition-colors shrink-0" />
                  </button>
                </td>

                {/* 5. Requests */}
                <td className="py-2.5 px-2.5 align-middle text-right font-mono text-xs font-medium text-foreground whitespace-nowrap">
                  {acc.total_requests.toLocaleString()}
                </td>

                {/* 6. Tokens */}
                <td className="py-2.5 px-2.5 align-middle text-right whitespace-nowrap">
                  <div
                    className="flex flex-col text-xs font-mono leading-tight gap-0.5 items-end"
                    title={`Входные: ${acc.total_prompt_tokens.toLocaleString()} | Выходные: ${acc.total_completion_tokens.toLocaleString()}`}
                  >
                    <span className="text-foreground/90 font-medium whitespace-nowrap">↓{formatTokens(acc.total_prompt_tokens)}</span>
                    <span className="text-muted-foreground text-[10px] whitespace-nowrap">↑{formatTokens(acc.total_completion_tokens)}</span>
                  </div>
                </td>

                {/* 7. Last used */}
                <td
                  className="py-2.5 px-2.5 align-middle text-right text-xs text-muted-foreground whitespace-nowrap"
                  title={acc.last_used_ts ? new Date(acc.last_used_ts * 1000).toLocaleString() : undefined}
                >
                  {formatRelativeTime(acc.last_used_ts)}
                </td>

                {/* 8. Actions */}
                <td className="py-2.5 px-3 align-middle text-right whitespace-nowrap">
                  <div className="flex items-center justify-end gap-1">
                    {acc.active ? (
                      <span className="inline-flex items-center justify-center gap-1 h-7 min-w-[72px] px-2 text-xs font-medium rounded-md bg-emerald-500/10 text-emerald-400 border border-emerald-500/25 select-none font-sans">
                        <Check className="w-3.5 h-3.5" />
                        <span>Активен</span>
                      </span>
                    ) : (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleActivate(acc)}
                        disabled={activatingId === acc.id}
                        className="h-7 min-w-[72px] text-xs px-2 gap-1 text-emerald-400 border-emerald-500/30 bg-emerald-500/5 hover:bg-emerald-500/15 cursor-pointer"
                        title="Сделать активным аккаунтом"
                      >
                        {activatingId === acc.id ? (
                          <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                          <CheckCircle2 className="w-3.5 h-3.5" />
                        )}
                        <span>Выбрать</span>
                      </Button>
                    )}
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setSelectedErrorAcc(acc)}
                      className="h-7 w-7 p-0 text-muted-foreground hover:text-foreground cursor-pointer shrink-0"
                      title="Логи ошибок аккаунта"
                    >
                      <AlertTriangle className="w-3.5 h-3.5 text-amber-400/80" />
                    </Button>
                    {onRelogin && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => onRelogin(acc)}
                        className="h-7 text-xs px-2 gap-1 text-primary border-primary/30 bg-primary/5 hover:bg-primary/15 cursor-pointer"
                        title="Релогин через Google OAuth"
                      >
                        <LogIn className="w-3.5 h-3.5" />
                        <span>Релогин</span>
                      </Button>
                    )}
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleDelete(acc)}
                      disabled={deletingId === acc.id}
                      className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive hover:border-destructive/40 hover:bg-destructive/10 cursor-pointer shrink-0"
                      title="Удалить аккаунт"
                    >
                      {deletingId === acc.id ? (
                        <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      ) : (
                        <Trash2 className="w-3.5 h-3.5" />
                      )}
                    </Button>
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
