import { useCallback, useEffect, useState, useRef } from 'react';
import { useApiKey } from './use-api-key';

export interface ChatItem {
  chat_id: string;
  title: string;
  total_requests: number;
  successful_requests: number;
  failed_requests: number;
  prompt_tokens: number;
  completion_tokens: number;
  cache_tokens: number;
  total_tokens: number;
  avg_latency_ms: number;
  first_ts: number;
  last_ts: number;
  models: string[];
  accounts: string[];
  endpoints: string[];
  last_error: string | null;
}

export interface RequestItem {
  id: number;
  ts: number;
  endpoint: string;
  model: string | null;
  pool_account: string | null;
  prompt_tokens: number;
  completion_tokens: number;
  cache_tokens: number;
  success: number | boolean;
  latency_ms: number | null;
  error_type: string | null;
  chat_id: string | null;
  chat_title: string | null;
  prompt_preview: string | null;
  response_preview: string | null;
}

export interface RequestsOverview {
  total_requests: number;
  total_chats: number;
  successful_requests: number;
  failed_requests: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_cache_tokens: number;
  avg_latency_ms: number;
  models: { model: string; count: number }[];
  endpoints: { endpoint: string; count: number }[];
}

export interface RequestFilters {
  search: string;
  model: string;
  endpoint: string;
  status: 'all' | 'success' | 'failed';
  windowHours: number | null;
  page: number;
  pageSize: number;
  viewMode: 'chats' | 'flat';
}

const DEFAULT_FILTERS: RequestFilters = {
  search: '',
  model: '',
  endpoint: '',
  status: 'all',
  windowHours: null,
  page: 1,
  pageSize: 20,
  viewMode: 'chats',
};

export function useRequests() {
  const { apiKey } = useApiKey();
  const [overview, setOverview] = useState<RequestsOverview | null>(null);
  const [chats, setChats] = useState<ChatItem[]>([]);
  const [totalChats, setTotalChats] = useState(0);
  const [requests, setRequests] = useState<RequestItem[]>([]);
  const [totalRequests, setTotalRequests] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState<RequestFilters>(DEFAULT_FILTERS);
  const [autoRefreshInterval, setAutoRefreshInterval] = useState<number>(0);

  // Cached requests per chat for expanded accordions
  const [chatRequestsCache, setChatRequestsCache] = useState<Record<string, RequestItem[]>>({});
  const [loadingChatId, setLoadingChatId] = useState<string | null>(null);

  const filtersRef = useRef(filters);
  filtersRef.current = filters;

  const fetchOverview = useCallback(async () => {
    if (!apiKey) return;
    try {
      const headers = { Authorization: `Bearer ${apiKey}` };
      const hoursParam = filtersRef.current.windowHours ? `?window_hours=${filtersRef.current.windowHours}` : '';
      const res = await fetch(`/v1/stats/overview${hoursParam}`, { headers });
      if (res.ok) {
        const data = await res.json();
        setOverview(data);
      }
    } catch {
      // ignore
    }
  }, [apiKey]);

  const fetchChats = useCallback(async () => {
    if (!apiKey) return;
    setLoading(true);
    setError(null);
    try {
      const headers = { Authorization: `Bearer ${apiKey}` };
      const current = filtersRef.current;
      const params = new URLSearchParams({
        limit: String(current.pageSize),
        offset: String((current.page - 1) * current.pageSize),
      });
      if (current.search.trim()) params.append('search', current.search.trim());
      if (current.model) params.append('model', current.model);
      if (current.endpoint) params.append('endpoint', current.endpoint);
      if (current.status !== 'all') params.append('status', current.status);
      if (current.windowHours) params.append('window_hours', String(current.windowHours));

      const res = await fetch(`/v1/stats/chats?${params.toString()}`, { headers });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setChats(data.chats || []);
      setTotalChats(data.total || 0);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch chats');
    } finally {
      setLoading(false);
    }
  }, [apiKey]);

  const fetchFlatRequests = useCallback(async () => {
    if (!apiKey) return;
    setLoading(true);
    setError(null);
    try {
      const headers = { Authorization: `Bearer ${apiKey}` };
      const current = filtersRef.current;
      const params = new URLSearchParams({
        limit: String(current.pageSize),
        offset: String((current.page - 1) * current.pageSize),
      });
      if (current.search.trim()) params.append('search', current.search.trim());
      if (current.model) params.append('model', current.model);
      if (current.endpoint) params.append('endpoint', current.endpoint);
      if (current.status !== 'all') params.append('status', current.status);
      if (current.windowHours) params.append('window_hours', String(current.windowHours));

      const res = await fetch(`/v1/stats/requests?${params.toString()}`, { headers });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setRequests(data.requests || []);
      setTotalRequests(data.total || 0);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch requests');
    } finally {
      setLoading(false);
    }
  }, [apiKey]);

  const refresh = useCallback(async () => {
    await fetchOverview();
    if (filtersRef.current.viewMode === 'chats') {
      await fetchChats();
    } else {
      await fetchFlatRequests();
    }
  }, [fetchOverview, fetchChats, fetchFlatRequests]);

  // Load chat details for a specific chat ID
  const fetchChatRequests = useCallback(
    async (chatId: string, force = false): Promise<RequestItem[]> => {
      if (!apiKey) return [];
      if (!force && chatRequestsCache[chatId]) {
        return chatRequestsCache[chatId];
      }
      setLoadingChatId(chatId);
      try {
        const headers = { Authorization: `Bearer ${apiKey}` };
        const res = await fetch(`/v1/stats/chats/${encodeURIComponent(chatId)}`, { headers });
        if (res.ok) {
          const data = await res.json();
          const reqs = data.requests || [];
          setChatRequestsCache((prev) => ({ ...prev, [chatId]: reqs }));
          return reqs;
        }
      } catch {
        // ignore
      } finally {
        setLoadingChatId(null);
      }
      return [];
    },
    [apiKey, chatRequestsCache]
  );

  const deleteChat = useCallback(
    async (chatId: string) => {
      if (!apiKey) return;
      try {
        const headers = { Authorization: `Bearer ${apiKey}` };
        const res = await fetch(`/v1/stats/chats/${encodeURIComponent(chatId)}`, {
          method: 'DELETE',
          headers,
        });
        if (res.ok) {
          setChatRequestsCache((prev) => {
            const next = { ...prev };
            delete next[chatId];
            return next;
          });
          await refresh();
        }
      } catch {
        // ignore
      }
    },
    [apiKey, refresh]
  );

  const clearHistory = useCallback(
    async (olderThanHours?: number) => {
      if (!apiKey) return;
      try {
        const headers = { Authorization: `Bearer ${apiKey}` };
        const param = olderThanHours ? `?older_than_hours=${olderThanHours}` : '';
        const res = await fetch(`/v1/stats/requests${param}`, {
          method: 'DELETE',
          headers,
        });
        if (res.ok) {
          setChatRequestsCache({});
          await refresh();
        }
      } catch {
        // ignore
      }
    },
    [apiKey, refresh]
  );

  const updateFilters = useCallback((updates: Partial<RequestFilters>) => {
    setFilters((prev) => {
      const next = { ...prev, ...updates };
      // If search/filter changed, reset page to 1 unless page is explicitly updated
      if (
        updates.page === undefined &&
        (updates.search !== undefined ||
          updates.model !== undefined ||
          updates.endpoint !== undefined ||
          updates.status !== undefined ||
          updates.windowHours !== undefined ||
          updates.viewMode !== undefined)
      ) {
        next.page = 1;
      }
      return next;
    });
  }, []);

  // Trigger fetch whenever filters change
  useEffect(() => {
    fetchOverview();
    if (filters.viewMode === 'chats') {
      fetchChats();
    } else {
      fetchFlatRequests();
    }
  }, [filters, fetchOverview, fetchChats, fetchFlatRequests]);

  // Auto-refresh interval
  useEffect(() => {
    if (!autoRefreshInterval || autoRefreshInterval <= 0) return;
    const timer = setInterval(() => {
      refresh();
    }, autoRefreshInterval);
    return () => clearInterval(timer);
  }, [autoRefreshInterval, refresh]);

  return {
    overview,
    chats,
    totalChats,
    requests,
    totalRequests,
    loading,
    loadingChatId,
    chatRequestsCache,
    error,
    filters,
    autoRefreshInterval,
    setAutoRefreshInterval,
    updateFilters,
    refresh,
    fetchChatRequests,
    deleteChat,
    clearHistory,
  };
}
