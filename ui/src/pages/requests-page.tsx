import { useState, useMemo } from 'react';
import {
  RefreshCw,
  Search,
  MessageSquare,
  CheckCircle2,
  XCircle,
  Clock,
  Zap,
  Coins,
  Copy,
  Check,
  ChevronDown,
  ChevronRight,
  Trash2,
  Layers,
  List,
  Eye,
  AlertTriangle,
  X,
  Bot,
  User,
  Shield,
  Hash,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { useRequests, type ChatItem, type RequestItem } from '../hooks/use-requests';

function formatTokens(n: number) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return n.toLocaleString();
}

function formatLatency(ms: number | null) {
  if (ms === null || ms === undefined) return '—';
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)}s`;
  return `${ms}ms`;
}

function formatRelativeTime(ts: number) {
  const diff = Date.now() / 1000 - ts;
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function formatExactTime(ts: number) {
  return new Date(ts * 1000).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function CopyButton({ text, label }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);

  const onCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <button
      onClick={onCopy}
      title="Copy to clipboard"
      className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors px-1.5 py-0.5 rounded bg-muted/60 hover:bg-muted"
    >
      {copied ? <Check className="w-3 h-3 text-emerald-500" /> : <Copy className="w-3 h-3" />}
      {label && <span>{copied ? 'Copied' : label}</span>}
    </button>
  );
}

function StatTile({
  label,
  value,
  subtext,
  icon,
}: {
  label: string;
  value: string | number;
  subtext?: string;
  icon?: React.ReactNode;
}) {
  return (
    <div className="border rounded-xl p-4 bg-card flex flex-col justify-between">
      <div className="flex items-center justify-between text-muted-foreground">
        <span className="text-xs font-medium uppercase tracking-wide">{label}</span>
        {icon && <span className="opacity-70">{icon}</span>}
      </div>
      <div className="mt-2">
        <div className="text-2xl font-bold tracking-tight">{value}</div>
        {subtext && <div className="text-xs text-muted-foreground mt-0.5">{subtext}</div>}
      </div>
    </div>
  );
}

function EndpointBadge({ endpoint }: { endpoint: string }) {
  let color = 'bg-blue-500/10 text-blue-400 border-blue-500/20';
  let label = endpoint;

  if (endpoint.includes('openai') || endpoint === 'openai-chat') {
    color = 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
    label = 'OpenAI Chat';
  } else if (endpoint.includes('anthropic')) {
    color = 'bg-amber-500/10 text-amber-400 border-amber-500/20';
    label = 'Anthropic';
  } else if (endpoint.includes('image')) {
    color = 'bg-purple-500/10 text-purple-400 border-purple-500/20';
    label = 'Image Gen';
  } else if (endpoint.includes('audio-speech')) {
    color = 'bg-pink-500/10 text-pink-400 border-pink-500/20';
    label = 'TTS';
  } else if (endpoint.includes('audio-transcription')) {
    color = 'bg-indigo-500/10 text-indigo-400 border-indigo-500/20';
    label = 'STT';
  }

  return (
    <span className={`px-2 py-0.5 rounded-full text-[11px] font-medium border ${color}`}>
      {label}
    </span>
  );
}

function RequestDetailModal({
  request,
  onClose,
}: {
  request: RequestItem;
  onClose: () => void;
}) {
  const [tab, setTab] = useState<'preview' | 'raw'>('preview');

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="bg-card border border-border rounded-2xl w-full max-w-4xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        {/* Modal Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border bg-muted/30">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-primary/10 text-primary">
              <Bot className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-semibold text-base flex items-center gap-2">
                Request #{request.id}
                <EndpointBadge endpoint={request.endpoint} />
                {Boolean(request.success) ? (
                  <span className="inline-flex items-center gap-1 text-xs text-emerald-500 font-medium bg-emerald-500/10 px-2 py-0.5 rounded-full">
                    <CheckCircle2 className="w-3 h-3" /> OK
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 text-xs text-destructive font-medium bg-destructive/10 px-2 py-0.5 rounded-full">
                    <XCircle className="w-3 h-3" /> Failed
                  </span>
                )}
              </h3>
              <p className="text-xs text-muted-foreground mt-0.5">
                {formatExactTime(request.ts)} ({formatRelativeTime(request.ts)})
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Metadata Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 p-4 border-b border-border bg-muted/10 text-xs">
          <div>
            <span className="text-muted-foreground block">Model</span>
            <span className="font-mono font-medium">{request.model || '—'}</span>
          </div>
          <div>
            <span className="text-muted-foreground block">Pool Account</span>
            <span className="font-mono font-medium">{request.pool_account || '—'}</span>
          </div>
          <div>
            <span className="text-muted-foreground block">Latency</span>
            <span className="font-medium">{formatLatency(request.latency_ms)}</span>
          </div>
          <div>
            <span className="text-muted-foreground block">Tokens (In / Out / Cache)</span>
            <span className="font-medium">
              {request.prompt_tokens.toLocaleString()} / {request.completion_tokens.toLocaleString()} / {request.cache_tokens.toLocaleString()}
            </span>
            <span className="text-muted-foreground block text-[11px] mt-0.5">
              Total: {(request.prompt_tokens + request.completion_tokens).toLocaleString()} (cache already in In)
            </span>
          </div>
        </div>

        {/* Modal Content Tabs */}
        <div className="flex border-b border-border px-6 pt-2 gap-4 text-sm bg-muted/20">
          <button
            onClick={() => setTab('preview')}
            className={`pb-2 font-medium border-b-2 transition-colors ${
              tab === 'preview' ? 'border-primary text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            Formatted View
          </button>
          <button
            onClick={() => setTab('raw')}
            className={`pb-2 font-medium border-b-2 transition-colors ${
              tab === 'raw' ? 'border-primary text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            Raw JSON
          </button>
        </div>

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {tab === 'preview' ? (
            <>
              {/* User Prompt */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                    <User className="w-3.5 h-3.5 text-primary" /> User Prompt
                  </span>
                  {request.prompt_preview && <CopyButton text={request.prompt_preview} label="Copy Prompt" />}
                </div>
                <div className="p-4 rounded-xl bg-muted/40 border border-border/80 text-sm whitespace-pre-wrap font-sans text-foreground select-text">
                  {request.prompt_preview || <span className="italic text-muted-foreground">No prompt recorded</span>}
                </div>
              </div>

              {/* Response or Error */}
              {Boolean(request.success) ? (
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                      <Bot className="w-3.5 h-3.5 text-emerald-500" /> Assistant Response
                    </span>
                    {request.response_preview && <CopyButton text={request.response_preview} label="Copy Response" />}
                  </div>
                  <div className="p-4 rounded-xl bg-muted/30 border border-border/80 text-sm prose dark:prose-invert max-w-none select-text">
                    {request.response_preview ? (
                      <ReactMarkdown>{request.response_preview}</ReactMarkdown>
                    ) : (
                      <span className="italic text-muted-foreground">No response recorded</span>
                    )}
                  </div>
                </div>
              ) : (
                <div className="space-y-2">
                  <span className="text-xs font-semibold uppercase tracking-wider text-destructive flex items-center gap-1.5">
                    <AlertTriangle className="w-3.5 h-3.5" /> Error Details
                  </span>
                  <div className="p-4 rounded-xl bg-destructive/10 border border-destructive/30 text-destructive text-sm font-mono whitespace-pre-wrap select-text">
                    <div className="font-bold mb-1">Error Type: {request.error_type || 'Unknown'}</div>
                    {request.response_preview || 'Request execution failed'}
                  </div>
                </div>
              )}
            </>
          ) : (
            <pre className="p-4 rounded-xl bg-muted/40 border border-border text-xs font-mono overflow-x-auto text-foreground">
              {JSON.stringify(request, null, 2)}
            </pre>
          )}
        </div>

        {/* Modal Footer */}
        <div className="flex items-center justify-between px-6 py-3 border-t border-border bg-muted/20">
          <div className="text-xs text-muted-foreground font-mono">
            Chat ID: {request.chat_id || 'legacy_' + request.id}
          </div>
          <Button variant="outline" size="sm" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
    </div>
  );
}

function ChatCard({
  chat,
  isExpanded,
  onToggle,
  requests,
  loadingRequests,
  onDelete,
  onInspectRequest,
}: {
  chat: ChatItem;
  isExpanded: boolean;
  onToggle: () => void;
  requests: RequestItem[] | undefined;
  loadingRequests: boolean;
  onDelete: () => void;
  onInspectRequest: (req: RequestItem) => void;
}) {
  const hasErrors = chat.failed_requests > 0;
  const [showAll, setShowAll] = useState(false);

  // Show newest requests at the top (reversed chronological: bottom to top)
  const orderedRequests = useMemo(() => {
    if (!requests) return [];
    return [...requests].reverse();
  }, [requests]);

  const displayedRequests = useMemo(() => {
    if (showAll || orderedRequests.length <= 10) return orderedRequests;
    return orderedRequests.slice(0, 10);
  }, [orderedRequests, showAll]);

  return (
    <div
      className={`border rounded-2xl transition-all duration-200 bg-card overflow-hidden ${
        isExpanded ? 'border-primary/50 shadow-md' : 'hover:border-border/80'
      }`}
    >
      {/* Chat Row Header */}
      <div
        onClick={onToggle}
        className="p-4 cursor-pointer hover:bg-muted/30 transition-colors flex flex-col gap-3"
      >
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3 min-w-0 flex-1">
            <button className="mt-0.5 p-1 rounded-md text-muted-foreground hover:text-foreground">
              {isExpanded ? <ChevronDown className="w-4 h-4 text-primary" /> : <ChevronRight className="w-4 h-4" />}
            </button>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 flex-wrap">
                <h4 className="font-semibold text-base text-foreground tracking-tight truncate max-w-xl">
                  {chat.title || `Chat ${chat.chat_id}`}
                </h4>
                {hasErrors ? (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-destructive/10 text-destructive border border-destructive/20">
                    <AlertTriangle className="w-3 h-3" /> {chat.failed_requests} failed
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                    <CheckCircle2 className="w-3 h-3" /> All OK
                  </span>
                )}
              </div>

              <div className="flex items-center gap-2 mt-1.5 flex-wrap text-xs text-muted-foreground">
                <span className="inline-flex items-center gap-1 font-mono text-[11px] bg-muted/60 px-1.5 py-0.5 rounded">
                  <Hash className="w-3 h-3 opacity-60" />
                  {chat.chat_id}
                  <CopyButton text={chat.chat_id} />
                </span>
                <span>•</span>
                <span className="font-medium text-foreground">{chat.total_requests} turn{chat.total_requests > 1 ? 's' : ''}</span>
                <span>•</span>
                <span>Last active {formatRelativeTime(chat.last_ts)}</span>
              </div>
            </div>
          </div>

          {/* Right Badges & Stats */}
          <div className="flex items-center gap-3 shrink-0">
            <div className="hidden sm:flex flex-col items-end text-right">
              <div className="text-xs font-semibold text-foreground flex items-center gap-1">
                <Coins className="w-3.5 h-3.5 text-amber-400" />
                {formatTokens(chat.total_tokens)} tokens
              </div>
              <div className="text-[11px] text-muted-foreground flex items-center gap-1 mt-0.5">
                <Clock className="w-3 h-3" />
                {formatLatency(chat.avg_latency_ms)} avg
              </div>
            </div>

            <button
              onClick={(e) => {
                e.stopPropagation();
                if (window.confirm(`Delete chat "${chat.title || chat.chat_id}" and all its history?`)) {
                  onDelete();
                }
              }}
              title="Delete chat session"
              className="p-1.5 rounded-lg text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Badges footer */}
        <div className="flex items-center gap-1.5 flex-wrap pt-1 text-xs">
          {chat.endpoints.map((ep) => (
            <EndpointBadge key={ep} endpoint={ep} />
          ))}
          {chat.models.map((m) => (
            <span
              key={m}
              className="px-2 py-0.5 rounded-full text-[11px] font-medium bg-muted text-muted-foreground border border-border/60"
            >
              {m}
            </span>
          ))}
          {chat.accounts.map((acc) => (
            <span
              key={acc}
              className="px-2 py-0.5 rounded-full text-[11px] font-mono font-medium bg-primary/10 text-primary border border-primary/20 flex items-center gap-1"
            >
              <Shield className="w-2.5 h-2.5" />
              {acc}
            </span>
          ))}
        </div>
      </div>

      {/* Expanded Accordion Body (Turns List) */}
      {isExpanded && (
        <div className="border-t border-border bg-muted/10 p-4 space-y-4 animate-in slide-in-from-top-2 duration-150">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Conversation Turns ({requests?.length || 0})
            </span>
            <span className="text-xs text-muted-foreground">Newest first</span>
          </div>

          {loadingRequests && !requests ? (
            <div className="text-xs text-muted-foreground flex items-center gap-2 py-4 justify-center">
              <RefreshCw className="w-4 h-4 animate-spin" /> Loading turn history…
            </div>
          ) : requests && requests.length > 0 ? (
            <div className="space-y-3">
              {displayedRequests.map((req) => {
                const turnIndex = requests ? requests.findIndex((r) => r.id === req.id) + 1 : 0;
                return (
                  <div
                    key={req.id}
                    className={`border rounded-xl p-4 bg-card transition-all ${
                      !Boolean(req.success) ? 'border-destructive/40 bg-destructive/5' : 'hover:border-border'
                    }`}
                  >
                    {/* Turn Header */}
                    <div className="flex items-center justify-between flex-wrap gap-2 pb-3 border-b border-border/60">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="px-2 py-0.5 rounded-md text-xs font-bold bg-primary/15 text-primary">
                          Turn #{turnIndex}
                        </span>
                        <span className="text-xs font-mono text-muted-foreground">
                          {formatExactTime(req.ts)}
                        </span>
                        <EndpointBadge endpoint={req.endpoint} />
                        {req.model && (
                          <span className="text-xs font-mono font-medium px-2 py-0.5 rounded bg-muted">
                            {req.model}
                          </span>
                        )}
                        {req.pool_account && (
                          <span className="text-xs font-mono text-primary flex items-center gap-1">
                            <Shield className="w-3 h-3" />
                            {req.pool_account}
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-3">
                        <div className="text-xs text-muted-foreground flex items-center gap-2 font-mono">
                          <span>{formatLatency(req.latency_ms)}</span>
                          <span>•</span>
                          <span>
                            {req.prompt_tokens + req.completion_tokens} tok
                          </span>
                        </div>

                        <Button
                          variant="ghost"
                          size="xs"
                          onClick={() => onInspectRequest(req)}
                          className="gap-1 text-xs text-muted-foreground hover:text-foreground"
                        >
                          <Eye className="w-3.5 h-3.5" /> Inspect
                        </Button>
                      </div>
                    </div>

                    {/* Prompt & Response Preview */}
                    <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                      {/* User Prompt */}
                      <div className="space-y-1">
                        <div className="flex items-center justify-between text-muted-foreground font-medium">
                          <span className="flex items-center gap-1 text-primary">
                            <User className="w-3 h-3" /> Prompt
                          </span>
                          {req.prompt_preview && <CopyButton text={req.prompt_preview} />}
                        </div>
                        <div className="p-2.5 rounded-lg bg-muted/40 border border-border/50 text-foreground font-sans line-clamp-4 select-text">
                          {req.prompt_preview || <span className="italic text-muted-foreground">No prompt text</span>}
                        </div>
                      </div>

                      {/* Assistant Response */}
                      <div className="space-y-1">
                        <div className="flex items-center justify-between text-muted-foreground font-medium">
                          <span className="flex items-center gap-1 text-emerald-500">
                            <Bot className="w-3 h-3" /> Response
                          </span>
                          {req.response_preview && <CopyButton text={req.response_preview} />}
                        </div>
                        {Boolean(req.success) ? (
                          <div className="p-2.5 rounded-lg bg-muted/20 border border-border/50 text-foreground font-sans line-clamp-4 select-text">
                            {req.response_preview || <span className="italic text-muted-foreground">No response text</span>}
                          </div>
                        ) : (
                          <div className="p-2.5 rounded-lg bg-destructive/10 border border-destructive/30 text-destructive font-mono line-clamp-4 select-text">
                            {req.error_type ? `[${req.error_type}] ` : ''}{req.response_preview || 'Error'}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}

              {orderedRequests.length > 10 && (
                <div className="flex justify-center pt-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setShowAll((prev) => !prev)}
                    className="text-xs"
                  >
                    {showAll
                      ? 'Show only last 10 turns'
                      : `Load remaining turns (${orderedRequests.length - 10} more)`}
                  </Button>
                </div>
              )}
            </div>
          ) : (
            <div className="text-xs text-muted-foreground py-4 text-center">
              No detailed requests recorded for this chat.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function RequestsPage() {
  const {
    overview,
    chats,
    totalChats,
    requests,
    totalRequests,
    loading,
    loadingChatId,
    chatRequestsCache,
    filters,
    autoRefreshInterval,
    setAutoRefreshInterval,
    updateFilters,
    refresh,
    fetchChatRequests,
    deleteChat,
    clearHistory,
  } = useRequests();

  const [expandedChatIds, setExpandedChatIds] = useState<Set<string>>(new Set());
  const [inspectingRequest, setInspectingRequest] = useState<RequestItem | null>(null);

  const toggleExpandChat = (chatId: string) => {
    setExpandedChatIds((prev) => {
      const next = new Set(prev);
      if (next.has(chatId)) {
        next.delete(chatId);
      } else {
        next.add(chatId);
        fetchChatRequests(chatId);
      }
      return next;
    });
  };

  const totalPages = useMemo(() => {
    const total = filters.viewMode === 'chats' ? totalChats : totalRequests;
    return Math.max(1, Math.ceil(total / filters.pageSize));
  }, [filters.viewMode, totalChats, totalRequests, filters.pageSize]);

  return (
    <div className="flex flex-col flex-1 h-full p-8 overflow-auto bg-background text-foreground">
      {/* Top Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Requests</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Monitor API requests, token stats, and conversation sessions grouped by chat.
          </p>
        </div>

        <div className="flex items-center gap-2.5 flex-wrap">
          {/* Auto Refresh Select */}
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground bg-card border rounded-lg px-2.5 py-1.5">
            <span>Auto:</span>
            <select
              value={autoRefreshInterval}
              onChange={(e) => setAutoRefreshInterval(Number(e.target.value))}
              className="bg-transparent text-foreground outline-none cursor-pointer font-medium"
            >
              <option value={0} className="bg-card">Off</option>
              <option value={5000} className="bg-card">5s</option>
              <option value={15000} className="bg-card">15s</option>
              <option value={30000} className="bg-card">30s</option>
            </select>
          </div>

          <Button
            onClick={refresh}
            disabled={loading}
            variant="outline"
            size="sm"
            className="gap-2"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>

          <Button
            onClick={() => {
              if (window.confirm('Clear all request logs and history from database?')) {
                clearHistory();
              }
            }}
            variant="destructive"
            size="sm"
            className="gap-1.5 text-xs"
          >
            <Trash2 className="w-3.5 h-3.5" />
            Clear
          </Button>
        </div>
      </div>

      {/* Overview Stat Cards */}
      {overview && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4 mb-6">
          <StatTile
            label="Total Requests"
            value={overview.total_requests.toLocaleString()}
            subtext={`${overview.successful_requests} ok / ${overview.failed_requests} failed`}
            icon={<Zap className="w-4 h-4 text-primary" />}
          />
          <StatTile
            label="Conversations"
            value={overview.total_chats.toLocaleString()}
            subtext="Unique chat sessions"
            icon={<MessageSquare className="w-4 h-4 text-emerald-400" />}
          />
          <StatTile
            label="Success Rate"
            value={
              overview.total_requests > 0
                ? `${((overview.successful_requests / overview.total_requests) * 100).toFixed(1)}%`
                : '100%'
            }
            subtext={`${overview.failed_requests} errors`}
            icon={<CheckCircle2 className="w-4 h-4 text-emerald-500" />}
          />
          <StatTile
            label="Tokens (IN / OUT)"
            value={`${formatTokens(overview.total_prompt_tokens)} / ${formatTokens(overview.total_completion_tokens)}`}
            subtext={`Total: ${formatTokens(overview.total_tokens ?? overview.total_prompt_tokens + overview.total_completion_tokens)} · cache ⊆ IN: ${formatTokens(overview.total_cache_tokens)}`}
            icon={<Coins className="w-4 h-4 text-amber-400" />}
          />
          <StatTile
            label="Avg Latency"
            value={formatLatency(overview.avg_latency_ms)}
            subtext="Per request"
            icon={<Clock className="w-4 h-4 text-blue-400" />}
          />
        </div>
      )}

      {/* Filter & Search Bar */}
      <div className="border rounded-2xl p-4 bg-card mb-6 space-y-3">
        <div className="flex flex-col md:flex-row items-stretch md:items-center gap-3">
          {/* Search Input */}
          <div className="relative flex-1">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={filters.search}
              onChange={(e) => updateFilters({ search: e.target.value })}
              placeholder="Search chat title, prompt, response, model, account, chat ID…"
              className="pl-9 pr-8 text-sm"
            />
            {filters.search && (
              <button
                onClick={() => updateFilters({ search: '' })}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>

          {/* View Mode Switcher */}
          <div className="flex items-center bg-muted/60 p-1 rounded-xl border border-border shrink-0">
            <button
              onClick={() => updateFilters({ viewMode: 'chats' })}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                filters.viewMode === 'chats'
                  ? 'bg-card text-foreground shadow-sm font-semibold'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <Layers className="w-3.5 h-3.5" />
              Grouped by Chat
            </button>
            <button
              onClick={() => updateFilters({ viewMode: 'flat' })}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                filters.viewMode === 'flat'
                  ? 'bg-card text-foreground shadow-sm font-semibold'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <List className="w-3.5 h-3.5" />
              Flat Requests
            </button>
          </div>
        </div>

        {/* Dropdown Filters Row */}
        <div className="flex items-center gap-2.5 flex-wrap pt-1 text-xs">
          {/* Endpoint select */}
          <select
            value={filters.endpoint}
            onChange={(e) => updateFilters({ endpoint: e.target.value })}
            className="bg-muted border border-border text-foreground rounded-lg px-2.5 py-1.5 outline-none font-medium cursor-pointer"
          >
            <option value="">All Endpoints</option>
            <option value="openai-chat">OpenAI Chat (/v1/chat/completions)</option>
            <option value="anthropic-chat">Anthropic (/anthropic/v1/messages)</option>
            <option value="image-generation">Image Gen (/v1/images/generations)</option>
            <option value="audio-speech">TTS (/v1/audio/speech)</option>
            <option value="audio-transcription">STT (/v1/audio/transcriptions)</option>
          </select>

          {/* Model select */}
          {overview?.models && overview.models.length > 0 && (
            <select
              value={filters.model}
              onChange={(e) => updateFilters({ model: e.target.value })}
              className="bg-muted border border-border text-foreground rounded-lg px-2.5 py-1.5 outline-none font-medium cursor-pointer font-mono"
            >
              <option value="">All Models</option>
              {overview.models.map((m) => (
                <option key={m.model} value={m.model}>
                  {m.model} ({m.count})
                </option>
              ))}
            </select>
          )}

          {/* Status select */}
          <select
            value={filters.status}
            onChange={(e) => updateFilters({ status: e.target.value as any })}
            className="bg-muted border border-border text-foreground rounded-lg px-2.5 py-1.5 outline-none font-medium cursor-pointer"
          >
            <option value="all">All Status</option>
            <option value="success">Success only</option>
            <option value="failed">Failed only</option>
          </select>

          {/* Time Window */}
          <select
            value={filters.windowHours === null ? '' : String(filters.windowHours)}
            onChange={(e) => updateFilters({ windowHours: e.target.value ? Number(e.target.value) : null })}
            className="bg-muted border border-border text-foreground rounded-lg px-2.5 py-1.5 outline-none font-medium cursor-pointer"
          >
            <option value="">All Time</option>
            <option value="1">Last 1 Hour</option>
            <option value="24">Last 24 Hours</option>
            <option value="168">Last 7 Days</option>
          </select>

          {/* Reset Filters button */}
          {(filters.search || filters.endpoint || filters.model || filters.status !== 'all' || filters.windowHours) && (
            <Button
              variant="ghost"
              size="xs"
              onClick={() =>
                updateFilters({
                  search: '',
                  endpoint: '',
                  model: '',
                  status: 'all',
                  windowHours: null,
                })
              }
              className="text-xs text-muted-foreground hover:text-foreground ml-auto"
            >
              Reset Filters
            </Button>
          )}
        </div>
      </div>

      {/* Main Content Area */}
      <div className="space-y-4 flex-1">
        {filters.viewMode === 'chats' ? (
          /* Grouped by Chat View */
          chats.length === 0 ? (
            <div className="border rounded-2xl p-12 bg-card text-center flex flex-col items-center justify-center space-y-3">
              <MessageSquare className="w-12 h-12 text-muted-foreground/40" />
              <div className="text-base font-medium">No conversation sessions found</div>
              <p className="text-sm text-muted-foreground max-w-sm">
                {filters.search || filters.model || filters.endpoint || filters.status !== 'all'
                  ? 'Try adjusting your search or filters to see results.'
                  : 'Start sending chat requests to see them grouped here in real-time.'}
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {chats.map((chat) => (
                <ChatCard
                  key={chat.chat_id}
                  chat={chat}
                  isExpanded={expandedChatIds.has(chat.chat_id)}
                  onToggle={() => toggleExpandChat(chat.chat_id)}
                  requests={chatRequestsCache[chat.chat_id]}
                  loadingRequests={loadingChatId === chat.chat_id}
                  onDelete={() => deleteChat(chat.chat_id)}
                  onInspectRequest={(req) => setInspectingRequest(req)}
                />
              ))}
            </div>
          )
        ) : (
          /* Flat Requests Table View */
          requests.length === 0 ? (
            <div className="border rounded-2xl p-12 bg-card text-center flex flex-col items-center justify-center space-y-3">
              <List className="w-12 h-12 text-muted-foreground/40" />
              <div className="text-base font-medium">No requests found</div>
              <p className="text-sm text-muted-foreground max-w-sm">
                Try adjusting your search or filters to see results.
              </p>
            </div>
          ) : (
            <div className="border rounded-2xl bg-card overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead className="bg-muted/50 text-muted-foreground border-b border-border">
                    <tr>
                      <th className="text-left p-3 font-semibold">ID / Time</th>
                      <th className="text-left p-3 font-semibold">Chat / Title</th>
                      <th className="text-left p-3 font-semibold">Endpoint</th>
                      <th className="text-left p-3 font-semibold">Model</th>
                      <th className="text-left p-3 font-semibold">Account</th>
                      <th className="text-left p-3 font-semibold">Status</th>
                      <th className="text-left p-3 font-semibold">Latency</th>
                      <th className="text-left p-3 font-semibold">Tokens (In / Out)</th>
                      <th className="text-right p-3 font-semibold">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {requests.map((req) => (
                      <tr key={req.id} className="hover:bg-muted/30 transition-colors">
                        <td className="p-3 whitespace-nowrap">
                          <div className="font-bold text-foreground">#{req.id}</div>
                          <div className="text-muted-foreground font-mono text-[11px]">
                            {formatRelativeTime(req.ts)}
                          </div>
                        </td>
                        <td className="p-3 max-w-xs truncate">
                          <div className="font-medium text-foreground truncate" title={req.chat_title || req.prompt_preview || ''}>
                            {req.chat_title || req.prompt_preview || `Request #${req.id}`}
                          </div>
                          <div className="font-mono text-[10px] text-muted-foreground">
                            {req.chat_id || 'legacy'}
                          </div>
                        </td>
                        <td className="p-3 whitespace-nowrap">
                          <EndpointBadge endpoint={req.endpoint} />
                        </td>
                        <td className="p-3 font-mono whitespace-nowrap text-foreground">
                          {req.model || '—'}
                        </td>
                        <td className="p-3 font-mono whitespace-nowrap text-primary">
                          {req.pool_account || '—'}
                        </td>
                        <td className="p-3 whitespace-nowrap">
                          {Boolean(req.success) ? (
                            <span className="inline-flex items-center gap-1 text-emerald-500 font-medium bg-emerald-500/10 px-2 py-0.5 rounded-full">
                              <CheckCircle2 className="w-3 h-3" /> OK
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 text-destructive font-medium bg-destructive/10 px-2 py-0.5 rounded-full">
                              <XCircle className="w-3 h-3" /> Fail
                            </span>
                          )}
                        </td>
                        <td className="p-3 whitespace-nowrap font-mono">
                          {formatLatency(req.latency_ms)}
                        </td>
                        <td className="p-3 whitespace-nowrap font-mono">
                          {req.prompt_tokens.toLocaleString()} / {req.completion_tokens.toLocaleString()}
                        </td>
                        <td className="p-3 text-right whitespace-nowrap">
                          <Button
                            variant="ghost"
                            size="xs"
                            onClick={() => setInspectingRequest(req)}
                            className="gap-1"
                          >
                            <Eye className="w-3.5 h-3.5" /> Inspect
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )
        )}
      </div>

      {/* Pagination Footer */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-4 mt-6 pt-4 border-t border-border text-xs text-muted-foreground">
        <div>
          Showing{' '}
          <span className="font-semibold text-foreground">
            {((filters.page - 1) * filters.pageSize) + 1}
          </span>{' '}
          to{' '}
          <span className="font-semibold text-foreground">
            {Math.min(filters.page * filters.pageSize, filters.viewMode === 'chats' ? totalChats : totalRequests)}
          </span>{' '}
          of{' '}
          <span className="font-semibold text-foreground">
            {filters.viewMode === 'chats' ? totalChats : totalRequests}
          </span>{' '}
          {filters.viewMode === 'chats' ? 'chats' : 'requests'}
        </div>

        <div className="flex items-center gap-2">
          {/* Page size select */}
          <select
            value={filters.pageSize}
            onChange={(e) => updateFilters({ pageSize: Number(e.target.value), page: 1 })}
            className="bg-card border border-border text-foreground rounded-lg px-2 py-1 outline-none cursor-pointer"
          >
            <option value={10}>10 / page</option>
            <option value={20}>20 / page</option>
            <option value={50}>50 / page</option>
            <option value={100}>100 / page</option>
          </select>

          {/* Page navigation */}
          <Button
            variant="outline"
            size="xs"
            disabled={filters.page <= 1}
            onClick={() => updateFilters({ page: filters.page - 1 })}
          >
            Prev
          </Button>

          <span className="px-2 font-medium text-foreground">
            Page {filters.page} of {totalPages}
          </span>

          <Button
            variant="outline"
            size="xs"
            disabled={filters.page >= totalPages}
            onClick={() => updateFilters({ page: filters.page + 1 })}
          >
            Next
          </Button>
        </div>
      </div>

      {/* Detail Modal */}
      {inspectingRequest && (
        <RequestDetailModal
          request={inspectingRequest}
          onClose={() => setInspectingRequest(null)}
        />
      )}
    </div>
  );
}
