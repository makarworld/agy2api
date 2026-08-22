import { Pencil } from 'lucide-react';
import { type PoolAccount } from '../hooks/use-stats';
import { useApiKey } from '../hooks/use-api-key';

export function AccountsTable({ accounts, poolEnabled, onChanged }: { accounts: PoolAccount[]; poolEnabled: boolean; onChanged: () => void }) {
  const { apiKey } = useApiKey();

  const editProxy = async (acc: PoolAccount) => {
    const next = window.prompt(
      `Proxy for "${acc.label}" (e.g. http://user:pass@host:port). Leave empty to clear:`,
      acc.proxy || ''
    );
    if (next === null) return; // cancelled
    await fetch(`/v1/accounts/${acc.id}/proxy`, {
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
            <th className="text-left p-3 font-medium">Label</th>
            <th className="text-left p-3 font-medium">Status</th>
            <th className="text-left p-3 font-medium">Proxy</th>
            <th className="text-left p-3 font-medium">Requests</th>
            <th className="text-left p-3 font-medium">Tokens IN/OUT</th>
            <th className="text-left p-3 font-medium">Last used</th>
          </tr>
        </thead>
        <tbody>
          {accounts.map((acc) => (
            <tr key={acc.id} className="border-t">
              <td className="p-3">
                {acc.label}
                {acc.active && <span className="ml-2 text-xs text-emerald-500">● active</span>}
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
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
