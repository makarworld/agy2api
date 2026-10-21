import React, { useState, useEffect } from 'react';
import { useApiKey } from '../hooks/use-api-key';
import { apiUrl } from '../lib/api';
import { Lock, AlertCircle, Loader2, KeyRound } from 'lucide-react';
import { Button } from './ui/button';
import { Input } from './ui/input';

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const { apiKey, saveApiKey, clearApiKey } = useApiKey();
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [unauthorizedPrompt, setUnauthorizedPrompt] = useState(false);
  const [authRequired, setAuthRequired] = useState<boolean | null>(null);

  useEffect(() => {
    // Check if backend requires admin password
    const checkAuthStatus = async () => {
      try {
        const res = await fetch(apiUrl('/v1/auth/status'));
        if (res.ok) {
          const data = await res.json();
          setAuthRequired(Boolean(data.auth_required));
        } else {
          setAuthRequired(false);
        }
      } catch {
        setAuthRequired(false);
      }
    };
    checkAuthStatus();
  }, []);

  useEffect(() => {
    const handleUnauthorized = () => {
      setUnauthorizedPrompt(true);
      setError('Запрос вернул 401: требуется пароль администратора.');
    };
    window.addEventListener('agy:unauthorized', handleUnauthorized);
    return () => {
      window.removeEventListener('agy:unauthorized', handleUnauthorized);
    };
  }, []);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!password.trim()) return;

    setLoading(true);
    setError(null);

    try {
      const res = await fetch(apiUrl('/v1/auth/verify'), {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${password.trim()}`,
        },
      });

      if (!res.ok) {
        throw new Error('Неверный пароль. Проверьте AGY_ADMIN_PASSWORD в файле .env');
      }

      saveApiKey(password.trim());
      setPassword('');
      setUnauthorizedPrompt(false);
      setAuthRequired(true);
      window.dispatchEvent(new CustomEvent('agy:auth-success'));
    } catch (err: any) {
      setError(err.message || 'Ошибка авторизации');
      clearApiKey();
    } finally {
      setLoading(false);
    }
  };

  const renderUnauthorizedModal = () => (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4 animate-in fade-in duration-200">
      <div className="w-full max-w-md space-y-5 rounded-2xl border border-border bg-card p-7 shadow-2xl text-card-foreground">
        <div className="flex flex-col items-center text-center space-y-2">
          <div className="rounded-full bg-amber-500/10 p-3 text-amber-500">
            <KeyRound className="h-6 w-6" />
          </div>
          <h2 className="text-xl font-bold tracking-tight">Требуется авторизация</h2>
          <p className="text-sm text-muted-foreground">
            Запросы возвращают 401. Введите пароль <code className="bg-muted px-1.5 py-0.5 rounded font-mono text-xs">AGY_ADMIN_PASSWORD</code> из <code className="bg-muted px-1.5 py-0.5 rounded text-xs font-mono">.env</code>
          </p>
        </div>

        <form onSubmit={handleLogin} className="space-y-4">
          <div className="space-y-2">
            <Input
              type="password"
              placeholder="AGY_ADMIN_PASSWORD..."
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={loading}
              autoFocus
            />
          </div>

          {error && (
            <div className="flex items-center gap-2 rounded-lg bg-destructive/10 p-3 text-sm text-destructive">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <div className="flex gap-2">
            <Button type="submit" disabled={loading || !password.trim()} className="w-full">
              {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              Применить пароль
            </Button>
          </div>
        </form>
      </div>
    </div>
  );

  // 1. If auth is not required by backend (first start on new system without AGY_ADMIN_PASSWORD):
  // grant full open access! No password screen.
  if (authRequired === false) {
    return (
      <>
        {children}
        {unauthorizedPrompt && renderUnauthorizedModal()}
      </>
    );
  }

  // 2. While checking auth status on first load:
  if (authRequired === null) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background text-muted-foreground text-xs">
        <Loader2 className="w-5 h-5 animate-spin mr-2" /> Загрузка AGY2API...
      </div>
    );
  }

  // 3. Auth IS required, and user has no key yet:
  if (!apiKey) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background p-4 text-foreground">
        <div className="w-full max-w-md space-y-6 rounded-2xl border bg-card p-8 shadow-xl">
          <div className="flex flex-col items-center text-center space-y-2">
            <div className="rounded-full bg-primary/10 p-3 text-primary">
              <Lock className="h-6 w-6" />
            </div>
            <h1 className="text-2xl font-bold tracking-tight">AGY2API Admin</h1>
            <p className="text-sm text-muted-foreground">
              Введите пароль <b>AGY_ADMIN_PASSWORD</b> из вашего файла <code className="bg-muted px-1.5 py-0.5 rounded text-xs">.env</code>
            </p>
          </div>

          <form onSubmit={handleLogin} className="space-y-4">
            <div className="space-y-2">
              <Input
                type="password"
                placeholder="AGY_ADMIN_PASSWORD..."
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={loading}
                autoFocus
              />
            </div>

            {error && (
              <div className="flex items-center gap-2 rounded-lg bg-destructive/10 p-3 text-sm text-destructive">
                <AlertCircle className="h-4 w-4 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <Button type="submit" disabled={loading || !password.trim()} className="w-full">
              {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              Войти
            </Button>
          </form>
        </div>
      </div>
    );
  }

  // 4. Auth is required, key exists, but 401 prompt can be shown on top
  return (
    <>
      {children}
      {unauthorizedPrompt && renderUnauthorizedModal()}
    </>
  );
}
