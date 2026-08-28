import { useState, useEffect } from 'react';
import { useApiKey } from '../hooks/use-api-key';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { apiUrl } from '../lib/api';
import {
  Key,
  Plus,
  Trash2,
  Copy,
  Check,
  Eye,
  EyeOff,
  RefreshCw,
  AlertCircle,
  CheckCircle2,
  Power,
} from 'lucide-react';

interface ManagedApiKey {
  key: string;
  name: string;
  is_active: boolean;
  is_master?: boolean;
  created_at: number;
  expires_at: number | null;
  daily_output_limit: number | null;
  used_output_today: number;
  last_reset_day?: string | null;
}

export function ApiKeysPage() {
  const { apiKey, saveApiKey } = useApiKey();
  const [inputValue, setInputValue] = useState(apiKey);
  const [saved, setSaved] = useState(false);

  // Managed keys state
  const [keysList, setKeysList] = useState<ManagedApiKey[]>([]);
  const [loading, setLoading] = useState(false);
  const [statusMsg, setStatusMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Create Form State
  const [name, setName] = useState('');
  const [expiresInDays, setExpiresInDays] = useState('');
  const [dailyOutputLimit, setDailyOutputLimit] = useState('');
  const [creating, setCreating] = useState(false);

  // Visibility & Copy State
  const [visibleKeys, setVisibleKeys] = useState<Record<string, boolean>>({});
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  // Sync state when apiKey loads from hook
  useEffect(() => {
    setInputValue(apiKey);
  }, [apiKey]);

  const authHeaders = {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${apiKey}`,
  };

  const handleSaveLocalKey = () => {
    saveApiKey(inputValue);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const loadKeys = async () => {
    if (!apiKey) return;
    setLoading(true);
    try {
      const res = await fetch(apiUrl('/v1/admin/keys'), { headers: authHeaders });
      if (!res.ok) {
        throw new Error('Failed to load keys or unauthorized');
      }
      const data = await res.json();
      setKeysList(data.keys || []);
    } catch (err: any) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadKeys();
  }, [apiKey]);

  const handleCreateKey = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;

    setCreating(true);
    setStatusMsg(null);
    try {
      const payload: { name: string; expires_in_days?: number; daily_output_limit?: number } = {
        name: name.trim(),
      };
      if (expiresInDays.trim()) {
        const days = parseInt(expiresInDays.trim(), 10);
        if (!isNaN(days) && days > 0) payload.expires_in_days = days;
      }
      if (dailyOutputLimit.trim()) {
        const limit = parseInt(dailyOutputLimit.trim(), 10);
        if (!isNaN(limit) && limit > 0) payload.daily_output_limit = limit;
      }

      const res = await fetch(apiUrl('/v1/admin/keys'), {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Failed to create key');
      }

      setName('');
      setExpiresInDays('');
      setDailyOutputLimit('');
      setStatusMsg({ type: 'success', text: 'API Key successfully created!' });
      await loadKeys();
    } catch (err: any) {
      setStatusMsg({ type: 'error', text: err.message });
    } finally {
      setCreating(false);
    }
  };

  const handleToggleActive = async (keyItem: ManagedApiKey) => {
    try {
      const res = await fetch(apiUrl(`/v1/admin/keys/${encodeURIComponent(keyItem.key)}`), {
        method: 'PATCH',
        headers: authHeaders,
        body: JSON.stringify({ is_active: !keyItem.is_active }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Failed to update key status');
      }
      await loadKeys();
    } catch (err: any) {
      setStatusMsg({ type: 'error', text: err.message });
    }
  };

  const handleDeleteKey = async (keyStr: string) => {
    if (!window.confirm('Are you sure you want to delete this API Key?')) return;
    try {
      const res = await fetch(apiUrl(`/v1/admin/keys/${encodeURIComponent(keyStr)}`), {
        method: 'DELETE',
        headers: authHeaders,
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Failed to delete key');
      }
      setStatusMsg({ type: 'success', text: 'Key deleted' });
      await loadKeys();
    } catch (err: any) {
      setStatusMsg({ type: 'error', text: err.message });
    }
  };

  const toggleVisibility = (keyStr: string) => {
    setVisibleKeys((prev) => ({ ...prev, [keyStr]: !prev[keyStr] }));
  };

  const handleCopy = (keyStr: string) => {
    navigator.clipboard.writeText(keyStr);
    setCopiedKey(keyStr);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  const maskKey = (keyStr: string) => {
    if (keyStr.length <= 10) return '••••••••';
    return `${keyStr.slice(0, 7)}...${keyStr.slice(-4)}`;
  };

  const getStatusBadge = (item: ManagedApiKey) => {
    const now = Date.now() / 1000;
    const isExpired = item.expires_at !== null && now > item.expires_at;
    const isLimitExceeded =
      item.daily_output_limit !== null &&
      item.daily_output_limit > 0 &&
      item.used_output_today >= item.daily_output_limit;

    if (!item.is_active) {
      return (
        <span className="px-2 py-0.5 rounded-full text-xs bg-muted text-muted-foreground font-medium border">
          Inactive
        </span>
      );
    }
    if (isExpired) {
      return (
        <span className="px-2 py-0.5 rounded-full text-xs bg-red-500/15 text-red-400 font-medium border border-red-500/30">
          Expired
        </span>
      );
    }
    if (isLimitExceeded) {
      return (
        <span className="px-2 py-0.5 rounded-full text-xs bg-amber-500/15 text-amber-400 font-medium border border-amber-500/30">
          Limit Exceeded
        </span>
      );
    }
    return (
      <span className="px-2 py-0.5 rounded-full text-xs bg-emerald-500/15 text-emerald-400 font-medium border border-emerald-500/30">
        Active
      </span>
    );
  };

  return (
    <div className="flex-1 p-8 overflow-auto">
      <div className="max-w-5xl mx-auto space-y-8">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">API Keys</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Manage your local master key and create limited API keys with token quotas.
          </p>
        </div>

        {statusMsg && (
          <div
            className={`p-3 rounded-lg text-sm flex items-center gap-2 ${
              statusMsg.type === 'success'
                ? 'bg-green-500/10 text-green-700 dark:text-green-300 border border-green-500/20'
                : 'bg-destructive/10 text-destructive border border-destructive/20'
            }`}
          >
            {statusMsg.type === 'success' ? (
              <CheckCircle2 className="w-4 h-4 shrink-0" />
            ) : (
              <AlertCircle className="w-4 h-4 shrink-0" />
            )}
            <span>{statusMsg.text}</span>
          </div>
        )}

        {/* Local Admin Secret Key */}
        <div className="p-6 border rounded-xl bg-card text-card-foreground shadow-sm">
          <div className="space-y-4 max-w-xl">
            <div className="space-y-2">
              <label className="text-sm font-medium flex items-center gap-2">
                <Key className="w-4 h-4 text-primary" />
                Admin Secret Key (AGY_API_KEY)
              </label>
              <Input
                type="password"
                placeholder="sk-..."
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                Stored in your browser local storage, used to authorize admin actions and backend requests.
              </p>
            </div>
            <Button onClick={handleSaveLocalKey} className="w-full sm:w-auto">
              {saved ? 'Saved!' : 'Save Key'}
            </Button>
          </div>
        </div>

        {/* Create API Key Form */}
        <div className="p-6 border rounded-xl bg-card text-card-foreground shadow-sm space-y-4">
          <h2 className="text-lg font-semibold tracking-tight flex items-center gap-2">
            <Plus className="w-5 h-5 text-primary" />
            Create New API Key
          </h2>
          <form onSubmit={handleCreateKey} className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="text-xs font-medium text-muted-foreground block mb-1">
                Name / Label <span className="text-destructive">*</span>
              </label>
              <Input
                placeholder="e.g. Claude Code / Cursor"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
              />
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground block mb-1">
                Expires in Days (Optional)
              </label>
              <Input
                type="number"
                min="1"
                placeholder="e.g. 30"
                value={expiresInDays}
                onChange={(e) => setExpiresInDays(e.target.value)}
              />
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground block mb-1">
                Daily Output Tokens Limit (Optional)
              </label>
              <Input
                type="number"
                min="1"
                placeholder="e.g. 100000"
                value={dailyOutputLimit}
                onChange={(e) => setDailyOutputLimit(e.target.value)}
              />
            </div>
            <div className="md:col-span-3 flex justify-end">
              <Button type="submit" disabled={creating || !name.trim()} className="gap-1.5">
                <Plus className="w-4 h-4" />
                {creating ? 'Creating...' : 'Generate API Key'}
              </Button>
            </div>
          </form>
        </div>

        {/* API Keys Table */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold tracking-tight">Generated API Keys</h2>
            <Button variant="outline" size="sm" onClick={loadKeys} disabled={loading} className="gap-1.5">
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
          </div>

          <div className="border rounded-xl bg-card overflow-x-auto shadow-sm">
            <table className="w-full text-sm text-left">
              <thead className="bg-muted/50 text-muted-foreground border-b text-xs uppercase tracking-wider">
                <tr>
                  <th className="p-3 font-medium">Name</th>
                  <th className="p-3 font-medium">API Key</th>
                  <th className="p-3 font-medium">Status</th>
                  <th className="p-3 font-medium">Daily Tokens Usage</th>
                  <th className="p-3 font-medium">Created</th>
                  <th className="p-3 font-medium">Expires</th>
                  <th className="p-3 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {keysList.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="p-6 text-center text-muted-foreground text-sm">
                      {loading ? 'Loading API keys...' : 'No API keys generated yet.'}
                    </td>
                  </tr>
                ) : (
                  keysList.map((k) => {
                    const isVisible = !!visibleKeys[k.key];
                    const isCopied = copiedKey === k.key;
                    const used = k.used_output_today || 0;
                    const limit = k.daily_output_limit;
                    const percent = limit ? Math.min(100, Math.round((used / limit) * 100)) : null;

                    return (
                      <tr key={k.key} className="hover:bg-muted/30 transition-colors">
                        <td className="p-3 font-medium">{k.name}</td>
                        <td className="p-3">
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-xs text-foreground bg-muted/60 px-2 py-1 rounded">
                              {isVisible ? k.key : maskKey(k.key)}
                            </span>
                            <button
                              type="button"
                              onClick={() => toggleVisibility(k.key)}
                              className="text-muted-foreground hover:text-foreground p-1 transition-colors"
                              title={isVisible ? 'Hide Key' : 'Show Key'}
                            >
                              {isVisible ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                            </button>
                            <button
                              type="button"
                              onClick={() => handleCopy(k.key)}
                              className="text-muted-foreground hover:text-foreground p-1 transition-colors"
                              title="Copy Key"
                            >
                              {isCopied ? (
                                <Check className="w-3.5 h-3.5 text-emerald-500" />
                              ) : (
                                <Copy className="w-3.5 h-3.5" />
                              )}
                            </button>
                          </div>
                        </td>
                        <td className="p-3">{getStatusBadge(k)}</td>
                        <td className="p-3">
                          {limit ? (
                            <div className="space-y-1 w-36">
                              <div className="flex justify-between text-xs font-mono">
                                <span>{used.toLocaleString()}</span>
                                <span className="text-muted-foreground">/ {limit.toLocaleString()}</span>
                              </div>
                              <div className="w-full h-1.5 bg-muted rounded-full overflow-hidden">
                                <div
                                  className={`h-full transition-all ${
                                    percent! >= 100
                                      ? 'bg-red-500'
                                      : percent! > 80
                                      ? 'bg-amber-500'
                                      : 'bg-emerald-500'
                                  }`}
                                  style={{ width: `${percent}%` }}
                                />
                              </div>
                            </div>
                          ) : (
                            <span className="text-xs font-mono text-muted-foreground">
                              {used.toLocaleString()} / ∞
                            </span>
                          )}
                        </td>
                        <td className="p-3 text-xs text-muted-foreground whitespace-nowrap">
                          {k.created_at ? new Date(k.created_at * 1000).toLocaleDateString() : '—'}
                        </td>
                        <td className="p-3 text-xs text-muted-foreground whitespace-nowrap">
                          {k.expires_at ? new Date(k.expires_at * 1000).toLocaleDateString() : 'Never'}
                        </td>
                        <td className="p-3 text-right whitespace-nowrap">
                          <div className="flex items-center justify-end gap-1">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleToggleActive(k)}
                              className={`h-8 px-2 text-xs gap-1 ${
                                k.is_active
                                  ? 'text-muted-foreground hover:text-amber-500'
                                  : 'text-emerald-500 hover:text-emerald-400'
                              }`}
                              title={k.is_active ? 'Deactivate Key' : 'Activate Key'}
                            >
                              <Power className="w-3.5 h-3.5" />
                              {k.is_active ? 'Disable' : 'Enable'}
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleDeleteKey(k.key)}
                              className="h-8 px-2 text-xs text-muted-foreground hover:text-destructive gap-1"
                              title="Delete Key"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                              Delete
                            </Button>
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
