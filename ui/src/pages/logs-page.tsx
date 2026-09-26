import { useEffect, useState, useMemo, useRef } from 'react';
import { useApiKey } from '../hooks/use-api-key';
import { RefreshCw, Terminal, Search, Copy, Check, ArrowDown, Trash2 } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { apiUrl } from '../lib/api';

export function LogsPage() {
  const { apiKey } = useApiKey();
  const [logs, setLogs] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [lines, setLines] = useState<number>(200);
  const [filter, setFilter] = useState('');
  const [copied, setCopied] = useState(false);
  const [autoScroll, setAutoScroll] = useState(true);
  const terminalRef = useRef<HTMLDivElement>(null);

  const fetchLogs = async () => {
    setLoading(true);
    try {
      const response = await fetch(apiUrl(`/v1/logs?lines=${lines}`), {
        headers: {
          Authorization: `Bearer ${apiKey}`,
        },
      });
      if (!response.ok) {
        setLogs(`Error: ${response.status} ${response.statusText}`);
      } else {
        const data = await response.json();
        setLogs(data.logs || 'Логи пусты.');
      }
    } catch (err: any) {
      setLogs(`Ошибка получения логов: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (apiKey) {
      fetchLogs();
    } else {
      setLogs('Сначала укажите API-ключ в настройках.');
    }
  }, [apiKey, lines]);

  useEffect(() => {
    if (autoScroll && terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [logs, autoScroll]);

  const filteredLogs = useMemo(() => {
    if (!filter.trim()) return logs;
    const q = filter.toLowerCase();
    return logs
      .split('\n')
      .filter((line) => line.toLowerCase().includes(q))
      .join('\n');
  }, [logs, filter]);

  const handleCopy = () => {
    navigator.clipboard.writeText(logs);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="flex flex-col flex-1 h-full p-6 md:p-8 overflow-hidden bg-background">
      {/* Page Header */}
      <div className="flex items-center justify-between mb-5 shrink-0 select-none">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2.5">
            <Terminal className="w-6 h-6 text-primary" />
            System Logs
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Вывод логов и трейсов запросов сервиса AGY2API в реальном времени.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5 bg-muted/50 border border-border/70 rounded-lg px-2.5 py-1 text-xs">
            <span className="text-muted-foreground">Строк:</span>
            <select
              value={lines}
              onChange={(e) => setLines(Number(e.target.value))}
              className="bg-transparent border-none outline-none font-mono text-xs text-foreground cursor-pointer"
            >
              <option value={100} className="bg-popover text-foreground">100</option>
              <option value={200} className="bg-popover text-foreground">200</option>
              <option value={500} className="bg-popover text-foreground">500</option>
              <option value={1000} className="bg-popover text-foreground">1000</option>
            </select>
          </div>

          <Button onClick={fetchLogs} disabled={loading} variant="outline" size="sm" className="gap-1.5 cursor-pointer">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Обновить
          </Button>
        </div>
      </div>

      {/* Terminal Window */}
      <div className="flex-1 border border-border/80 rounded-2xl bg-[#0b0f14] flex flex-col shadow-xl overflow-hidden min-h-0">
        {/* Terminal Header Bar */}
        <div className="h-10 px-4 bg-[#111822] border-b border-border/40 flex items-center justify-between shrink-0 select-none">
          <div className="flex items-center gap-2">
            <span className="w-3 h-3 rounded-full bg-rose-500/80 inline-block" />
            <span className="w-3 h-3 rounded-full bg-amber-500/80 inline-block" />
            <span className="w-3 h-3 rounded-full bg-emerald-500/80 inline-block" />
            <span className="text-xs font-mono text-muted-foreground ml-2">agy2api.log</span>
          </div>

          <div className="flex items-center gap-3">
            <div className="relative flex items-center">
              <Search className="w-3.5 h-3.5 text-muted-foreground absolute left-2" />
              <Input
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                placeholder="Фильтр по тексту..."
                className="h-7 text-xs pl-7 pr-2 w-48 bg-[#0b0f14] border-border/50 text-foreground font-mono"
              />
            </div>

            <Button
              size="sm"
              variant="ghost"
              onClick={() => setAutoScroll(!autoScroll)}
              className={`h-7 px-2 text-xs gap-1 cursor-pointer ${
                autoScroll ? 'text-primary' : 'text-muted-foreground'
              }`}
              title="Автопрокрутка вниз"
            >
              <ArrowDown className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Auto-scroll</span>
            </Button>

            <Button
              size="sm"
              variant="ghost"
              onClick={handleCopy}
              className="h-7 px-2 text-xs gap-1 text-muted-foreground hover:text-foreground cursor-pointer"
              title="Копировать все логи"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5 text-muted-foreground" />}
              <span className="hidden sm:inline">{copied ? 'Скопировано' : 'Копировать'}</span>
            </Button>

            <Button
              size="sm"
              variant="ghost"
              onClick={() => setLogs('')}
              className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive cursor-pointer"
              title="Очистить экран"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </Button>
          </div>
        </div>

        {/* Terminal Content */}
        <div ref={terminalRef} className="flex-1 p-4 overflow-auto text-xs font-mono text-zinc-200 leading-relaxed select-text space-y-0.5">
          {filteredLogs.split('\n').map((line, idx) => {
            let color = 'text-zinc-300';
            if (line.includes('| ERROR')) color = 'text-rose-400 font-semibold bg-rose-500/10 rounded px-1 -mx-1';
            else if (line.includes('| WARNING')) color = 'text-amber-400 font-semibold';
            else if (line.includes('| INFO')) color = 'text-emerald-400/90';
            else if (line.includes('[oauth]')) color = 'text-sky-300';

            return (
              <div key={idx} className={`whitespace-pre-wrap break-all hover:bg-white/5 py-0.5 px-1 -mx-1 rounded transition-colors ${color}`}>
                {line || ' '}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
