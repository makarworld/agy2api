import { useEffect, useRef, useState } from 'react';
import { RefreshCw, UserPlus, X } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { AccountsTable } from '../components/accounts-table';
import { useStats } from '../hooks/use-stats';
import { useApiKey } from '../hooks/use-api-key';

type FlowState = 'idle' | 'starting' | 'pending' | 'saving';

export function PoolPage() {
  const { apiKey } = useApiKey();
  const { accounts, poolEnabled, loading, refresh } = useStats();
  const [proxy, setProxy] = useState('');
  const [flowState, setFlowState] = useState<FlowState>('idle');
  const [message, setMessage] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);

  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  useEffect(() => stopPolling, []);

  const authHeaders = { 'Content-Type': 'application/json', Authorization: `Bearer ${apiKey}` };

  const startAddAccount = async () => {
    setFlowState('starting');
    setMessage(null);
    const res = await fetch('/v1/accounts/add-flow/start', {
      method: 'POST',
      headers: authHeaders,
      body: JSON.stringify({ proxy: proxy.trim() || null }),
    });
    const data = await res.json();
    setMessage(data.message || (data.auto_added_current ?? null));
    if (data.auto_added_current) refresh();
    setFlowState('pending');

    pollRef.current = window.setInterval(async () => {
      const statusRes = await fetch('/v1/accounts/add-flow/status', { headers: authHeaders });
      const status = await statusRes.json();
      if (status.changed) {
        stopPolling();
        setFlowState('saving');
        const label = window.prompt('New Google account signed in! Give it a label:', 'account-2');
        if (label) {
          await fetch('/v1/accounts', {
            method: 'POST',
            headers: authHeaders,
            body: JSON.stringify({ label, proxy: proxy.trim() || null }),
          });
        }
        await fetch('/v1/accounts/add-flow/cancel', { method: 'POST', headers: authHeaders });
        setFlowState('idle');
        setMessage(label ? `Added "${label}" to the pool.` : null);
        refresh();
      }
    }, 3000);
  };

  const cancelFlow = async () => {
    stopPolling();
    await fetch('/v1/accounts/add-flow/cancel', { method: 'POST', headers: authHeaders });
    setFlowState('idle');
    setMessage(null);
  };

  return (
    <div className="flex flex-col flex-1 h-full p-8 overflow-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Account Pool</h1>
          <p className="text-sm text-muted-foreground mt-1">
            All agy accounts connected to the rotation pool.
          </p>
        </div>
        <Button onClick={refresh} disabled={loading} variant="outline" size="sm" className="gap-2">
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      <div className="border rounded-xl p-4 bg-card mb-6 space-y-3">
        {flowState === 'idle' ? (
          <div className="flex items-end gap-3">
            <div className="flex-1">
              <label className="text-xs text-muted-foreground uppercase tracking-wide">
                Proxy (optional)
              </label>
              <Input
                value={proxy}
                onChange={(e) => setProxy(e.target.value)}
                placeholder="http://user:pass@host:port"
                className="mt-1"
              />
            </div>
            <Button onClick={startAddAccount} className="gap-2">
              <UserPlus className="w-4 h-4" />
              Add Account
            </Button>
          </div>
        ) : (
          <div className="flex items-center justify-between">
            <div className="text-sm">
              {flowState === 'starting' && 'Opening login terminal…'}
              {flowState === 'pending' && (message || 'Waiting for you to sign in with the new account…')}
              {flowState === 'saving' && 'Saving new account…'}
            </div>
            {flowState !== 'saving' && (
              <Button onClick={cancelFlow} variant="outline" size="sm" className="gap-2">
                <X className="w-4 h-4" />
                Cancel
              </Button>
            )}
          </div>
        )}
      </div>

      <AccountsTable accounts={accounts} poolEnabled={poolEnabled} onChanged={refresh} />
    </div>
  );
}
