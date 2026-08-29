import { useState } from 'react';
import { RefreshCw, UserPlus, ExternalLink, Check, Copy, AlertCircle, Gauge } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { AccountsTable } from '../components/accounts-table';
import { useStats } from '../hooks/use-stats';
import { useApiKey } from '../hooks/use-api-key';
import { apiUrl } from '../lib/api';

export function PoolPage() {
  const { apiKey } = useApiKey();
  const { accounts, poolEnabled, loading, refresh } = useStats();

  const [label, setLabel] = useState('');
  const [proxy, setProxy] = useState('');
  const [authUrl, setAuthUrl] = useState<string | null>(null);
  const [flowId, setFlowId] = useState<string | null>(null);
  const [authCode, setAuthCode] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [generatingUrl, setGeneratingUrl] = useState(false);
  const [refreshingQuotas, setRefreshingQuotas] = useState(false);
  const [copied, setCopied] = useState(false);
  const [statusMsg, setStatusMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const authHeaders = { 'Content-Type': 'application/json', Authorization: `Bearer ${apiKey}` };

  const refreshAllQuotas = async () => {
    setRefreshingQuotas(true);
    try {
      await fetch(apiUrl('/v1/accounts/refresh-quotas'), {
        method: 'POST',
        headers: authHeaders,
      });
      await refresh();
      setStatusMsg({ type: 'success', text: 'Quotas refreshed successfully for all accounts.' });
    } catch (err: any) {
      setStatusMsg({ type: 'error', text: err.message || 'Failed to refresh quotas' });
    } finally {
      setRefreshingQuotas(false);
    }
  };

  const startOAuth = async (overrideProxy?: string) => {
    setGeneratingUrl(true);
    setStatusMsg(null);
    try {
      const activeProxy = overrideProxy !== undefined ? overrideProxy : proxy;
      const q = activeProxy.trim() ? `?proxy=${encodeURIComponent(activeProxy.trim())}` : '';
      const res = await fetch(apiUrl(`/v1/accounts/oauth/start${q}`), { headers: authHeaders });
      if (!res.ok) throw new Error('Failed to generate authorization URL');
      const data = await res.json();
      setAuthUrl(data.url);
      setFlowId(data.flow_id);
    } catch (err: any) {
      setStatusMsg({ type: 'error', text: err.message || 'Error generating auth link' });
    } finally {
      setGeneratingUrl(false);
    }
  };

  const handleRelogin = (acc: any) => {
    const accLabel = acc.label || acc.id;
    const accProxy = acc.proxy || '';
    setLabel(accLabel);
    setProxy(accProxy);
    setAuthCode('');
    setAuthUrl(null);
    setFlowId(null);
    window.scrollTo({ top: 0, behavior: 'smooth' });
    startOAuth(accProxy);
  };

  const copyUrl = () => {
    if (!authUrl) return;
    navigator.clipboard.writeText(authUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const completeOAuth = async () => {
    if (!authCode.trim()) {
      setStatusMsg({ type: 'error', text: 'Please paste the authorization code or redirect URL' });
      return;
    }
    setSubmitting(true);
    setStatusMsg(null);
    try {
      const res = await fetch(apiUrl('/v1/accounts/oauth/complete'), {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({
          flow_id: flowId,
          code: authCode.trim(),
          label: label.trim() || undefined,
          proxy: proxy.trim() || undefined,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to connect account');

      setStatusMsg({
        type: 'success',
        text: `Account "${data.label}" (${data.email || data.id}) connected successfully!`,
      });
      setAuthUrl(null);
      setFlowId(null);
      setAuthCode('');
      setLabel('');
      refresh();
    } catch (err: any) {
      setStatusMsg({ type: 'error', text: err.message || 'Failed to exchange OAuth code' });
    } finally {
      setSubmitting(false);
    }
  };

  const resetForm = () => {
    setAuthUrl(null);
    setFlowId(null);
    setAuthCode('');
    setStatusMsg(null);
  };

  return (
    <div className="flex flex-col flex-1 h-full p-8 overflow-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Account Pool</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Google Antigravity accounts connected for automatic rotation and quota sharing.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            onClick={refreshAllQuotas}
            disabled={loading || refreshingQuotas}
            variant="outline"
            size="sm"
            className="gap-2"
            title="Force query Google API to refresh remaining quota limits for all accounts"
          >
            <Gauge className={`w-4 h-4 ${refreshingQuotas ? 'animate-spin' : ''}`} />
            Refresh Quotas
          </Button>
          <Button onClick={refresh} disabled={loading} variant="outline" size="sm" className="gap-2">
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </div>
      </div>

      <div className="border rounded-xl p-5 bg-card mb-6 space-y-4">
        <h2 className="text-sm font-semibold tracking-wide flex items-center gap-2">
          <UserPlus className="w-4 h-4 text-primary" />
          Add Account via Google OAuth
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-12 gap-3 items-end">
          <div className="md:col-span-4">
            <label className="text-xs text-muted-foreground uppercase tracking-wide">
              Account Label (optional)
            </label>
            <Input
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="e.g. personal, work-2"
              className="mt-1"
            />
          </div>
          <div className="md:col-span-5">
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
          <div className="md:col-span-3">
            <Button
              onClick={() => startOAuth()}
              disabled={generatingUrl}
              className="w-full gap-2"
            >
              {generatingUrl ? 'Generating...' : authUrl ? 'Regenerate Link' : 'Generate Login Link'}
            </Button>
          </div>
        </div>

        {authUrl && (
          <div className="space-y-4 border-t pt-4">
            <div className="bg-muted/40 p-3 rounded-lg flex flex-col md:flex-row items-center justify-between gap-3">
              <div className="text-xs text-muted-foreground break-all flex-1 font-mono">
                {authUrl}
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <Button size="sm" variant="outline" onClick={copyUrl} className="gap-1">
                  {copied ? <Check className="w-3.5 h-3.5 text-green-500" /> : <Copy className="w-3.5 h-3.5" />}
                  {copied ? 'Copied' : 'Copy Link'}
                </Button>
                <a href={authUrl} target="_blank" rel="noreferrer">
                  <Button size="sm" className="gap-1">
                    <ExternalLink className="w-3.5 h-3.5" />
                    Open Google Sign-In
                  </Button>
                </a>
              </div>
            </div>

            <div className="space-y-2">
              <label className="text-xs font-medium">
                Paste Authorization Code or Redirect URL:
              </label>
              <div className="flex gap-2">
                <Input
                  value={authCode}
                  onChange={(e) => setAuthCode(e.target.value)}
                  placeholder="4/0ATsMZq... or https://antigravity.google/oauth-callback?code=..."
                  className="font-mono text-sm"
                />
                <Button
                  onClick={completeOAuth}
                  disabled={submitting || !authCode.trim()}
                  className="shrink-0"
                >
                  {submitting ? 'Connecting...' : 'Connect Account'}
                </Button>
                <Button variant="ghost" onClick={resetForm} disabled={submitting}>
                  Cancel
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                Sign in with the Google account in your browser (make sure to select/switch to the <b>target</b> Google account if multiple profiles exist), then copy the code displayed on page (or from the URL) and paste it above.
              </p>
            </div>
          </div>
        )}

        {statusMsg && (
          <div
            className={`p-3 rounded-lg text-sm flex items-center gap-2 ${
              statusMsg.type === 'success'
                ? 'bg-green-500/10 text-green-700 dark:text-green-300 border border-green-500/20'
                : 'bg-destructive/10 text-destructive border border-destructive/20'
            }`}
          >
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{statusMsg.text}</span>
          </div>
        )}
      </div>

      <AccountsTable
        accounts={accounts}
        poolEnabled={poolEnabled}
        onChanged={refresh}
        onRelogin={handleRelogin}
      />
    </div>
  );
}
