import React, { useState } from 'react';
import { useApiKey } from '../hooks/use-api-key';
import { apiUrl } from '../lib/api';
import { Lock, AlertCircle, Loader2 } from 'lucide-react';
import { Button } from './ui/button';
import { Input } from './ui/input';

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const { apiKey, saveApiKey, clearApiKey } = useApiKey();
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
        throw new Error('Неверный пароль');
      }

      saveApiKey(password.trim());
      setPassword('');
    } catch (err: any) {
      setError(err.message || 'Ошибка авторизации');
      clearApiKey();
    } finally {
      setLoading(false);
    }
  };

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
              Введите пароль администратора для доступа к панели
            </p>
          </div>

          <form onSubmit={handleLogin} className="space-y-4">
            <div className="space-y-2">
              <Input
                type="password"
                placeholder="Пароль администратора..."
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

  return <>{children}</>;
}
