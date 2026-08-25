import { useState, useEffect } from 'react';
import { Settings as SettingsIcon, Save, RefreshCw, CheckCircle2, AlertCircle } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { useApiKey } from '../hooks/use-api-key';
import { apiUrl } from '../lib/api';

export function SettingsPage() {
  const { apiKey } = useApiKey();
  const [settings, setSettings] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [statusMsg, setStatusMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const authHeaders = {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${apiKey}`,
  };

  const loadSettings = async () => {
    setLoading(true);
    setStatusMsg(null);
    try {
      const res = await fetch(apiUrl('/v1/settings'), { headers: authHeaders });
      if (!res.ok) throw new Error('Не удалось загрузить настройки');
      const data = await res.json();
      setSettings(data.settings || {});
    } catch (err: any) {
      setStatusMsg({ type: 'error', text: err.message });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSettings();
  }, [apiKey]);

  const handleToggle = (key: string) => {
    setSettings((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const handleChange = (key: string, val: string) => {
    setSettings((prev) => ({ ...prev, [key]: val }));
  };

  const handleSave = async () => {
    setSaving(true);
    setStatusMsg(null);
    try {
      const res = await fetch(apiUrl('/v1/settings'), {
        method: 'PUT',
        headers: authHeaders,
        body: JSON.stringify({ settings }),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Ошибка сохранения настроек');
      }
      setStatusMsg({ type: 'success', text: 'Настройки успешно применены и сохранены в .env' });
    } catch (err: any) {
      setStatusMsg({ type: 'error', text: err.message });
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center p-8">
        <RefreshCw className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="flex flex-col flex-1 h-full p-8 overflow-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
            <SettingsIcon className="w-6 h-6 text-primary" />
            Настройки
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Управление параметрами окружения и переключателями в реальном времени.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={loadSettings} disabled={loading} className="gap-1.5">
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Обновить
          </Button>
          <Button size="sm" onClick={handleSave} disabled={saving} className="gap-1.5">
            <Save className="w-4 h-4" />
            {saving ? 'Сохранение...' : 'Сохранить изменения'}
          </Button>
        </div>
      </div>

      {statusMsg && (
        <div
          className={`p-3 rounded-lg text-sm flex items-center gap-2 mb-6 ${
            statusMsg.type === 'success'
              ? 'bg-green-500/10 text-green-700 dark:text-green-300 border border-green-500/20'
              : 'bg-destructive/10 text-destructive border border-destructive/20'
          }`}
        >
          {statusMsg.type === 'success' ? (
            <CheckCircle2 className="w-4 h-4 shrink-0" />
          ) : (
            <AlertCircle className="w-4 h-4 shrink-0" />
          )}
          <span>{statusMsg.text}</span>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Group 1: Transport & Models */}
        <div className="border rounded-xl p-5 bg-card space-y-4">
          <h2 className="text-sm font-semibold tracking-wide uppercase text-muted-foreground border-b pb-2">
            Транспорт и Модели
          </h2>
          <div>
            <label className="text-xs font-medium">AGY_TRANSPORT (http / warm / cli)</label>
            <Input
              value={settings.AGY_TRANSPORT || ''}
              onChange={(e) => handleChange('AGY_TRANSPORT', e.target.value)}
              placeholder="http"
              className="mt-1 font-mono text-sm"
            />
          </div>
          <div>
            <label className="text-xs font-medium">AGY_FORCE_MODEL (Принудительная модель)</label>
            <Input
              value={settings.AGY_FORCE_MODEL || ''}
              onChange={(e) => handleChange('AGY_FORCE_MODEL', e.target.value)}
              placeholder="max-gem"
              className="mt-1 font-mono text-sm"
            />
          </div>
          <div>
            <label className="text-xs font-medium">AGY_WARM_IDLE_TIMEOUT_SECONDS</label>
            <Input
              value={settings.AGY_WARM_IDLE_TIMEOUT_SECONDS || ''}
              onChange={(e) => handleChange('AGY_WARM_IDLE_TIMEOUT_SECONDS', e.target.value)}
              placeholder="600"
              className="mt-1 font-mono text-sm"
            />
          </div>
          <div>
            <label className="text-xs font-medium">AGY_WARM_MAX_SESSIONS</label>
            <Input
              value={settings.AGY_WARM_MAX_SESSIONS || ''}
              onChange={(e) => handleChange('AGY_WARM_MAX_SESSIONS', e.target.value)}
              placeholder="20"
              className="mt-1 font-mono text-sm"
            />
          </div>
        </div>

        {/* Group 2: Account Pool */}
        <div className="border rounded-xl p-5 bg-card space-y-4">
          <h2 className="text-sm font-semibold tracking-wide uppercase text-muted-foreground border-b pb-2">
            Пул Аккаунтов (Account Pool)
          </h2>
          <div className="flex items-center justify-between py-1">
            <div>
              <div className="text-sm font-medium">AGY_POOL_ENABLED</div>
              <div className="text-xs text-muted-foreground">Использовать пул аккаунтов для ротации</div>
            </div>
            <input
              type="checkbox"
              checked={!!settings.AGY_POOL_ENABLED}
              onChange={() => handleToggle('AGY_POOL_ENABLED')}
              className="w-5 h-5 rounded accent-primary cursor-pointer"
            />
          </div>
          <div className="flex items-center justify-between py-1">
            <div>
              <div className="text-sm font-medium">AGY_POOL_GIT_AUTOSYNC</div>
              <div className="text-xs text-muted-foreground">Автоматическая синхронизация через Git</div>
            </div>
            <input
              type="checkbox"
              checked={!!settings.AGY_POOL_GIT_AUTOSYNC}
              onChange={() => handleToggle('AGY_POOL_GIT_AUTOSYNC')}
              className="w-5 h-5 rounded accent-primary cursor-pointer"
            />
          </div>
          <div>
            <label className="text-xs font-medium">AGY_POOL_COOLDOWN_SECONDS (Кулдаун при 429)</label>
            <Input
              value={settings.AGY_POOL_COOLDOWN_SECONDS || ''}
              onChange={(e) => handleChange('AGY_POOL_COOLDOWN_SECONDS', e.target.value)}
              placeholder="3600"
              className="mt-1 font-mono text-sm"
            />
          </div>
          <div>
            <label className="text-xs font-medium">AGY_POOL_MAX_RETRIES</label>
            <Input
              value={settings.AGY_POOL_MAX_RETRIES || ''}
              onChange={(e) => handleChange('AGY_POOL_MAX_RETRIES', e.target.value)}
              placeholder="3"
              className="mt-1 font-mono text-sm"
            />
          </div>
        </div>

        {/* Group 3: HTTP, Tools & Response Tuning */}
        <div className="border rounded-xl p-5 bg-card space-y-4">
          <h2 className="text-sm font-semibold tracking-wide uppercase text-muted-foreground border-b pb-2">
            HTTP и Форматирование
          </h2>
          <div className="flex items-center justify-between py-1">
            <div>
              <div className="text-sm font-medium">AGY_THOUGHT_AS_TEXT</div>
              <div className="text-xs text-muted-foreground">Выводить рассуждения (thinking) в текст</div>
            </div>
            <input
              type="checkbox"
              checked={!!settings.AGY_THOUGHT_AS_TEXT}
              onChange={() => handleToggle('AGY_THOUGHT_AS_TEXT')}
              className="w-5 h-5 rounded accent-primary cursor-pointer"
            />
          </div>
          <div className="flex items-center justify-between py-1">
            <div>
              <div className="text-sm font-medium">AGY_HTTP_TRIM_TOOL_RESULTS</div>
              <div className="text-xs text-muted-foreground">Обрезать большие результаты инструментов</div>
            </div>
            <input
              type="checkbox"
              checked={!!settings.AGY_HTTP_TRIM_TOOL_RESULTS}
              onChange={() => handleToggle('AGY_HTTP_TRIM_TOOL_RESULTS')}
              className="w-5 h-5 rounded accent-primary cursor-pointer"
            />
          </div>
          <div className="flex items-center justify-between py-1">
            <div>
              <div className="text-sm font-medium">AGY_HTTP_EMPTY_AS_EMPTY_CONTENT</div>
              <div className="text-xs text-muted-foreground">Возвращать пустой ответ вместо ошибки STOP</div>
            </div>
            <input
              type="checkbox"
              checked={!!settings.AGY_HTTP_EMPTY_AS_EMPTY_CONTENT}
              onChange={() => handleToggle('AGY_HTTP_EMPTY_AS_EMPTY_CONTENT')}
              className="w-5 h-5 rounded accent-primary cursor-pointer"
            />
          </div>
          <div className="flex items-center justify-between py-1">
            <div>
              <div className="text-sm font-medium">AGY_AUTO_CLASSIFIER_SHORTCUT</div>
              <div className="text-xs text-muted-foreground">Быстрый классификатор запросов</div>
            </div>
            <input
              type="checkbox"
              checked={!!settings.AGY_AUTO_CLASSIFIER_SHORTCUT}
              onChange={() => handleToggle('AGY_AUTO_CLASSIFIER_SHORTCUT')}
              className="w-5 h-5 rounded accent-primary cursor-pointer"
            />
          </div>
          <div className="flex items-center justify-between py-1">
            <div>
              <div className="text-sm font-medium">AGY_HTTP_DEBUG</div>
              <div className="text-xs text-muted-foreground">Подробное логирование HTTP запросов</div>
            </div>
            <input
              type="checkbox"
              checked={!!settings.AGY_HTTP_DEBUG}
              onChange={() => handleToggle('AGY_HTTP_DEBUG')}
              className="w-5 h-5 rounded accent-primary cursor-pointer"
            />
          </div>
        </div>

        {/* Group 4: Proxy & OAuth */}
        <div className="border rounded-xl p-5 bg-card space-y-4">
          <h2 className="text-sm font-semibold tracking-wide uppercase text-muted-foreground border-b pb-2">
            Прокси и OAuth
          </h2>
          <div>
            <label className="text-xs font-medium">AGY_GOOGLE_PROXY (Глобальный прокси)</label>
            <Input
              value={settings.AGY_GOOGLE_PROXY || ''}
              onChange={(e) => handleChange('AGY_GOOGLE_PROXY', e.target.value)}
              placeholder="http://user:pass@host:port"
              className="mt-1 font-mono text-sm"
            />
          </div>
          <div className="flex items-center justify-between py-1">
            <div>
              <div className="text-sm font-medium">AGY_OAUTH_REFRESH_ENABLED</div>
              <div className="text-xs text-muted-foreground">Автоматический рефреш OAuth токенов</div>
            </div>
            <input
              type="checkbox"
              checked={!!settings.AGY_OAUTH_REFRESH_ENABLED}
              onChange={() => handleToggle('AGY_OAUTH_REFRESH_ENABLED')}
              className="w-5 h-5 rounded accent-primary cursor-pointer"
            />
          </div>
          <div className="flex items-center justify-between py-1">
            <div>
              <div className="text-sm font-medium">AGY_SSL_VERIFY</div>
              <div className="text-xs text-muted-foreground">Проверка SSL сертификатов (выключите для HTTP Toolkit)</div>
            </div>
            <input
              type="checkbox"
              checked={!!settings.AGY_SSL_VERIFY}
              onChange={() => handleToggle('AGY_SSL_VERIFY')}
              className="w-5 h-5 rounded accent-primary cursor-pointer"
            />
          </div>
          <div>
            <label className="text-xs font-medium">AGY_OAUTH_REFRESH_SKEW_SECONDS</label>
            <Input
              value={settings.AGY_OAUTH_REFRESH_SKEW_SECONDS || ''}
              onChange={(e) => handleChange('AGY_OAUTH_REFRESH_SKEW_SECONDS', e.target.value)}
              placeholder="120"
              className="mt-1 font-mono text-sm"
            />
          </div>
        </div>
      </div>
    </div>
  );
}
