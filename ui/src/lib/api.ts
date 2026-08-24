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
