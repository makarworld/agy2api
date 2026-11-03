import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useApiKey } from '../hooks/use-api-key';
import { useI18n } from '../lib/i18n';
import { apiUrl } from '../lib/api';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import {
  Users,
  MessageSquare,
  ArrowRight,
  CheckCircle2,
  AlertCircle,
  Copy,
  Check,
  RefreshCw,
  Play,
  Loader2,
  Sparkles,
} from 'lucide-react';

export function QuickstartPage() {
  const { apiKey } = useApiKey();
  const { t } = useI18n();

  // Step 1: Account count state
  const [accountCount, setAccountCount] = useState<number | null>(null);
  const [loadingAccounts, setLoadingAccounts] = useState(true);

  // Step 3: Claude CLI state
  const [cliStatus, setCliStatus] = useState<any>(null);
  const [loadingCli, setLoadingCli] = useState(true);
  const [selectedModel, setSelectedModel] = useState('max-gem');
  const [submittingCli, setSubmittingCli] = useState(false);
  const [cliMsg, setCliMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  const authHeaders = {
    'Content-Type': 'application/json',
    ...(apiKey ? { Authorization: `Bearer ${apiKey}` } : {}),
  };

  const fetchAccounts = async () => {
    setLoadingAccounts(true);
    try {
      const res = await fetch(apiUrl('/v1/accounts'), { headers: authHeaders });
      if (res.ok) {
        const data = await res.json();
        setAccountCount(Array.isArray(data.accounts) ? data.accounts.length : 0);
      }
    } catch {
      // ignore
    } finally {
      setLoadingAccounts(false);
    }
  };

  const fetchCliStatus = async () => {
    setLoadingCli(true);
    try {
      const res = await fetch(apiUrl('/v1/claude-cli/status'), { headers: authHeaders });
      if (res.ok) {
        const data = await res.json();
        setCliStatus(data);
        if (data.current_model) {
          setSelectedModel(data.current_model);
        }
      }
    } catch {
      // ignore
    } finally {
      setLoadingCli(false);
    }
  };

  useEffect(() => {
    fetchAccounts();
    fetchCliStatus();
  }, [apiKey]);

  const handleSetupCli = async (launch: boolean) => {
    setSubmittingCli(true);
    setCliMsg(null);
    try {
      const res = await fetch(apiUrl('/v1/claude-cli/setup'), {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({
          model: selectedModel,
          api_key: apiKey,
          launch,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to setup gclaude');
      }
      if (launch) {
        setCliMsg({ type: 'success', text: `Terminal launched with gclaude (${selectedModel})!` });
      } else {
        setCliMsg({
          type: 'success',
          text: `gclaude.bat saved to ${data.bat_path} (${selectedModel})! Command gclaude is ready in any terminal.`,
        });
      }
      await fetchCliStatus();
    } catch (err: any) {
      setCliMsg({ type: 'error', text: err.message || 'Setup error' });
    } finally {
      setSubmittingCli(false);
    }
  };

  const copyText = (txt: string, id: string) => {
    navigator.clipboard.writeText(txt);
    setCopiedKey(id);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  return (
    <div className="flex-1 p-6 md:p-8 overflow-auto">
      <div className="max-w-5xl mx-auto w-full space-y-8">
        {/* Header Hero */}
        <div className="space-y-2">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary/10 text-primary text-xs font-medium border border-primary/20">
            <Sparkles className="w-3.5 h-3.5" />
            <span>{t.qsBadge}</span>
          </div>
          <h1 className="text-3xl font-bold tracking-tight text-foreground">
            {t.qsTitle}
          </h1>
          <p className="text-sm text-muted-foreground max-w-3xl leading-relaxed">
            {t.qsSubtitle}
          </p>
        </div>

        {/* Steps List */}
        <div className="space-y-6">
          {/* STEP 1 */}
          <div className="border border-border/70 rounded-2xl bg-card p-6 shadow-sm relative overflow-hidden transition-all hover:border-primary/40">
            <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
              <div className="flex items-start gap-4">
                <div className="w-9 h-9 rounded-xl bg-primary/15 text-primary flex items-center justify-center font-bold text-sm shrink-0 border border-primary/25">
                  1
                </div>
                <div className="space-y-2">
                  <div className="flex items-center gap-3">
                    <h2 className="text-lg font-semibold text-foreground">
                      {t.qsStep1Title}
                    </h2>
                    {!loadingAccounts && accountCount !== null && (
                      <span
                        className={`text-xs px-2.5 py-0.5 rounded-full font-medium border ${
                          accountCount > 0
                            ? 'bg-emerald-500/15 text-emerald-500 border-emerald-500/30'
                            : 'bg-amber-500/15 text-amber-500 border-amber-500/30'
                        }`}
                      >
                        {accountCount > 0 ? `${t.qsAccountsInPool}${accountCount}` : t.qsNoAccounts}
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-muted-foreground leading-relaxed max-w-2xl">
                    {t.qsStep1Desc}
                  </p>
                </div>
              </div>

              <Link to="/pool" className="shrink-0 self-start md:self-center">
                <Button className="gap-2 text-xs font-semibold">
                  <Users className="w-4 h-4" />
                  {t.qsStep1Button}
                  <ArrowRight className="w-4 h-4" />
                </Button>
              </Link>
            </div>
          </div>

          {/* STEP 2 */}
          <div className="border border-border/70 rounded-2xl bg-card p-6 shadow-sm relative overflow-hidden transition-all hover:border-primary/40">
            <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
              <div className="flex items-start gap-4">
                <div className="w-9 h-9 rounded-xl bg-primary/15 text-primary flex items-center justify-center font-bold text-sm shrink-0 border border-primary/25">
                  2
                </div>
                <div className="space-y-2">
                  <h2 className="text-lg font-semibold text-foreground">
                    {t.qsStep2Title}
                  </h2>
                  <p className="text-sm text-muted-foreground leading-relaxed max-w-2xl">
                    {t.qsStep2Desc}
                  </p>
                </div>
              </div>

              <Link to="/chat" className="shrink-0 self-start md:self-center">
                <Button variant="outline" className="gap-2 text-xs font-semibold">
                  <MessageSquare className="w-4 h-4" />
                  {t.qsStep2Button}
                  <ArrowRight className="w-4 h-4" />
                </Button>
              </Link>
            </div>
          </div>

          {/* STEP 3 */}
          <div className="border border-border/70 rounded-2xl bg-card p-6 shadow-sm relative overflow-hidden space-y-5 transition-all hover:border-primary/40">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div className="flex items-start gap-4">
                <div className="w-9 h-9 rounded-xl bg-primary/15 text-primary flex items-center justify-center font-bold text-sm shrink-0 border border-primary/25">
                  3
                </div>
                <div className="space-y-1">
                  <div className="flex items-center gap-3">
                    <h2 className="text-lg font-semibold text-foreground">
                      {t.qsStep3Title}
                    </h2>
                    {!loadingCli && cliStatus && (
                      <span
                        className={`text-xs px-2.5 py-0.5 rounded-full font-medium border ${
                          cliStatus.installed
                            ? 'bg-emerald-500/15 text-emerald-500 border-emerald-500/30'
                            : 'bg-amber-500/15 text-amber-500 border-amber-500/30'
                        }`}
                      >
                        {cliStatus.installed ? t.qsCliInstalled : t.qsCliNotFound}
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-muted-foreground max-w-2xl leading-relaxed">
                    {t.qsStep3Desc}
                  </p>
                </div>
              </div>

              <div className="shrink-0 flex items-center gap-2">
                <button
                  onClick={() => copyText('gclaude', 'run_cmd')}
                  className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-muted hover:bg-muted/80 text-foreground font-mono transition-colors border cursor-pointer"
                  title="Copy launch command"
                >
                  {copiedKey === 'run_cmd' ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
                  <span className="font-bold">gclaude</span>
                </button>
              </div>
            </div>

            {loadingCli ? (
              <div className="p-4 flex items-center gap-2 text-xs text-muted-foreground border rounded-xl bg-muted/20">
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>{t.qsCheckingCli}</span>
              </div>
            ) : !cliStatus?.installed ? (
              /* If Claude is NOT installed: show install guide */
              <div className="p-4 rounded-xl border border-amber-500/30 bg-amber-500/5 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-xs font-semibold text-foreground">
                    <AlertCircle className="w-4 h-4 text-amber-500" />
                    <span>{t.qsInstallGuideTitle}</span>
                  </div>
                  <Button variant="outline" size="sm" onClick={fetchCliStatus} className="gap-1.5 text-xs h-8 cursor-pointer">
                    <RefreshCw className="w-3.5 h-3.5" />
                    {t.checkAgain}
                  </Button>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                  {/* Windows PowerShell */}
                  <div className="p-3 rounded-lg border bg-background/80 space-y-2">
                    <div className="flex items-center justify-between font-medium text-foreground">
                      <span>Windows (PowerShell)</span>
                      <button
                        onClick={() => copyText(cliStatus?.install_guide?.powershell || 'irm https://storage.googleapis.com/claude-code-dist/install.ps1 | iex', 'ps')}
                        className="inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground px-2 py-0.5 rounded bg-muted cursor-pointer"
                      >
                        {copiedKey === 'ps' ? <Check className="w-3 h-3 text-emerald-500" /> : <Copy className="w-3 h-3" />}
                        <span>{copiedKey === 'ps' ? t.copied : t.copy}</span>
                      </button>
                    </div>
                    <pre className="font-mono text-[11px] bg-muted/60 p-2 rounded overflow-x-auto text-muted-foreground select-all">
                      {cliStatus?.install_guide?.powershell || 'irm https://storage.googleapis.com/claude-code-dist/install.ps1 | iex'}
                    </pre>
                  </div>

                  {/* npm */}
                  <div className="p-3 rounded-lg border bg-background/80 space-y-2">
                    <div className="flex items-center justify-between font-medium text-foreground">
                      <span>npm (Node.js 18+)</span>
                      <button
                        onClick={() => copyText(cliStatus?.install_guide?.npm || 'npm install -g @anthropic-ai/claude-code', 'npm')}
                        className="inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground px-2 py-0.5 rounded bg-muted cursor-pointer"
                      >
                        {copiedKey === 'npm' ? <Check className="w-3 h-3 text-emerald-500" /> : <Copy className="w-3 h-3" />}
                        <span>{copiedKey === 'npm' ? t.copied : t.copy}</span>
                      </button>
                    </div>
                    <pre className="font-mono text-[11px] bg-muted/60 p-2 rounded overflow-x-auto text-muted-foreground select-all">
                      {cliStatus?.install_guide?.npm || 'npm install -g @anthropic-ai/claude-code'}
                    </pre>
                  </div>
                </div>
              </div>
            ) : (
              /* If Claude is installed: controls */
              <div className="p-4 rounded-xl border bg-muted/20 space-y-3">
                <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
                  <div className="flex items-center gap-2 flex-1 max-w-sm">
                    <label className="text-xs font-medium text-muted-foreground whitespace-nowrap">{t.qsModelLabel}</label>
                    <Input
                      value={selectedModel}
                      onChange={(e) => setSelectedModel(e.target.value)}
                      placeholder="max-gem"
                      className="h-9 text-xs font-mono"
                    />
                  </div>

                  <div className="flex items-center gap-2">
                    <Button
                      size="sm"
                      onClick={() => handleSetupCli(true)}
                      disabled={submittingCli}
                      className="h-9 gap-1.5 text-xs bg-primary hover:bg-primary/90 text-primary-foreground font-medium cursor-pointer"
                    >
                      {submittingCli ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
                      {t.qsLaunchButton} ({selectedModel})
                    </Button>

                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleSetupCli(false)}
                      disabled={submittingCli}
                      className="h-9 gap-1.5 text-xs cursor-pointer"
                    >
                      {t.qsUpdateButton}
                    </Button>
                  </div>
                </div>

                {cliMsg && (
                  <div
                    className={`p-3 rounded-lg text-xs flex items-center gap-2 ${
                      cliMsg.type === 'success'
                        ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20'
                        : 'bg-destructive/10 text-destructive border border-destructive/20'
                    }`}
                  >
                    {cliMsg.type === 'success' ? <CheckCircle2 className="w-4 h-4 shrink-0" /> : <AlertCircle className="w-4 h-4 shrink-0" />}
                    <span>{cliMsg.text}</span>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
