import { useEffect, useState } from 'react';
import { useApiKey } from '../hooks/use-api-key';
import { RefreshCw, Terminal } from 'lucide-react';
import { Button } from '../components/ui/button';
import { apiUrl } from '../lib/api';

export function LogsPage() {
  const { apiKey } = useApiKey();
  const [logs, setLogs] = useState<string>('Loading logs...');
  const [loading, setLoading] = useState(false);

  const fetchLogs = async () => {
    setLoading(true);
    try {
      const response = await fetch(apiUrl('/v1/logs?lines=100'), {
        headers: {
          'Authorization': `Bearer ${apiKey}`
        }
      });
      if (!response.ok) {
        setLogs(`Error: ${response.status} ${response.statusText}`);
      } else {
        const data = await response.json();
        setLogs(data.logs || 'No logs available.');
      }
    } catch (err: any) {
      setLogs(`Fetch error: ${err.message}`);
    }
    setLoading(false);
  };

  useEffect(() => {
    if (apiKey) {
      fetchLogs();
    } else {
      setLogs('Please configure your API key first.');
    }
  }, [apiKey]);

  return (
    <div className="flex flex-col flex-1 h-full p-8 overflow-hidden">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">System Logs</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Real-time output from the AGY wrapper service.
          </p>
        </div>
        <Button onClick={fetchLogs} disabled={loading} variant="outline" size="sm" className="gap-2">
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      <div className="flex-1 border rounded-xl bg-[#0d1117] text-[#e6edf3] font-mono-code text-sm p-4 overflow-auto shadow-inner relative">
        <div className="absolute top-4 right-4 text-[#8b949e]">
          <Terminal className="w-5 h-5" />
        </div>
        <pre className="whitespace-pre-wrap">{logs}</pre>
      </div>
    </div>
  );
}
