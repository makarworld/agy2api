export function getApiBaseUrl(): string {
  // Returns base URL prefix taking into account deployment under subpaths (e.g. /port26767)
  const base = import.meta.env.BASE_URL || '/';
  return base.endsWith('/') ? base.slice(0, -1) : base;
}

export function apiUrl(path: string): string {
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  const base = getApiBaseUrl();
  return `${base}${cleanPath}`;
}

// Global 401 fetch interceptor: notifies app when API rejects credentials
if (typeof window !== 'undefined' && !(window as any).__agy_fetch_intercepted__) {
  (window as any).__agy_fetch_intercepted__ = true;
  const originalFetch = window.fetch;
  window.fetch = async function (...args) {
    const res = await originalFetch.apply(this, args);
    if (res.status === 401) {
      const url = typeof args[0] === 'string' ? args[0] : (args[0] as Request)?.url || '';
      // Don't trigger popup loop on verify endpoint itself
      if (!url.includes('/auth/verify')) {
        window.dispatchEvent(new CustomEvent('agy:unauthorized'));
      }
    }
    return res;
  };
}
