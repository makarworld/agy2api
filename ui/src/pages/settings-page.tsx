import { useState, useEffect } from 'react';
import {
  Settings as SettingsIcon,
  Save,
  RefreshCw,
  CheckCircle2,
  AlertCircle,
  Plus,
  Trash2,
  Cpu,
  Users,
  Sliders,
  ShieldCheck,
  Layers,
} from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Switch } from '../components/ui/switch';
import { Select } from '../components/ui/select';
import { useApiKey } from '../hooks/use-api-key';
import { apiUrl } from '../lib/api';
import { buildThoughtTemplate, parseThoughtTemplate } from '../lib/thought-template';

const KNOWN_BACKEND_MODELS = [
  'gemini-3.8-flash-tiered',
  'gemini-3.8-flash-high',
  'gemini-3.8-flash-medium',
  'gemini-3.8-flash-low',
  'gemini-3.7-flash-high',
  'gemini-3.7-flash-medium',
  'gemini-3.7-flash-low',
  'gemini-3.6-flash-high',
  'gemini-3.6-flash-medium',
  'gemini-3.6-flash-low',
  'gemini-pro-agent',
  'gemini-3.1-pro-low',
  'claude-sonnet-4-6',
  'claude-opus-4-6-thinking',
  'gpt-oss-120b-medium',
];

interface ModelAliasRow {
  alias: string;
  target: string;
}

function parseAliasesString(raw: string): ModelAliasRow[] {
  let parsed: ModelAliasRow[] = [];
  const trimmed = (raw || '').trim();
  if (trimmed.startsWith('{')) {
    try {
      const obj = JSON.parse(trimmed);
      parsed = Object.entries(obj).map(([alias, target]) => ({ alias, target: String(target) }));
    } catch {
      // fallback
    }
  } else if (trimmed) {
    parsed = trimmed
      .split(',')
      .map((item) => item.trim())
      .filter((item) => item.includes('='))
      .map((item) => {
        const [alias, ...rest] = item.split('=');
        return { alias: alias.trim(), target: rest.join('=').trim() };
      })
      .filter((row) => row.alias && row.target);
  }

  // Ensure default max-gem is present as first row if not already defined
  const hasMaxGem = parsed.some((r) => r.alias === 'max-gem');
  if (!hasMaxGem) {
    parsed.unshift({ alias: 'max-gem', target: 'gemini-3.8-flash-high' });
  }

  return parsed;
}

function serializeAliases(rows: ModelAliasRow[]): string {
  return rows
    .filter((r) => r.alias.trim() && r.target.trim())
    .map((r) => `${r.alias.trim()}=${r.target.trim()}`)
    .join(', ');
}

interface SettingToggleRowProps {
  title: string;
  description: string;
  checked: boolean;
  onCheckedChange: () => void;
}

function SettingToggleRow({ title, description, checked, onCheckedChange }: SettingToggleRowProps) {
  return (
    <div
      onClick={onCheckedChange}
      className="flex items-center justify-between p-3 rounded-lg border border-border/50 bg-muted/20 hover:bg-muted/40 dark:bg-black/20 dark:hover:bg-black/35 hover:border-border/80 transition-all cursor-pointer select-none"
    >
      <div className="pr-4">
        <div className="text-sm font-medium leading-none">{title}</div>
        <div className="text-xs text-muted-foreground mt-1 leading-snug">{description}</div>
      </div>
      <Switch checked={checked} onCheckedChange={onCheckedChange} onClick={(e) => e.stopPropagation()} />
    </div>
  );
}

export function SettingsPage() {
  const { apiKey } = useApiKey();
  const [settings, setSettings] = useState<Record<string, any>>({});
  const [aliases, setAliases] = useState<ModelAliasRow[]>([]);
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [thoughtTemplate, setThoughtTemplate] = useState('<think>\\n{...}\\n</think>\\n\\n');
  const [statusMsg, setStatusMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const authHeaders = {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${apiKey}`,
  };

  const loadSettings = async () => {
    setLoading(true);
    setStatusMsg(null);
    try {
      const [resSettings, resModels] = await Promise.all([
        fetch(apiUrl('/v1/settings'), { headers: authHeaders }),
        fetch(apiUrl('/v1/models'), { headers: authHeaders }).catch(() => null),
      ]);
      if (!resSettings.ok) throw new Error('Не удалось загрузить настройки');
      const data = await resSettings.json();
      const loaded = data.settings || {};
      const parsedAliases = parseAliasesString(loaded.AGY_MODEL_ALIASES || '');
      setThoughtTemplate(
        buildThoughtTemplate(
          loaded.AGY_THOUGHT_TEXT_PREFIX || '<think>\n',
          loaded.AGY_THOUGHT_TEXT_SUFFIX || '\n</think>\n\n',
        ),
      );
      setAliases(parsedAliases);
      setSettings({
        ...loaded,
        AGY_MODEL_ALIASES: serializeAliases(parsedAliases),
      });

      if (resModels && resModels.ok) {
        const mData = await resModels.json();
        const mList = (mData.data || [])
          .map((m: any) => m.id)
          .filter((id: string) => !id.includes(' ')); // only clean model slugs
        const merged = [...KNOWN_BACKEND_MODELS];
        for (const id of mList) {
          if (!merged.includes(id)) merged.push(id);
        }
        setAvailableModels([...merged, ...parsedAliases.map((a) => a.alias).filter((a) => a && !merged.includes(a))]);
      } else {
        setAvailableModels([...KNOWN_BACKEND_MODELS, ...parsedAliases.map((a) => a.alias).filter((a) => !KNOWN_BACKEND_MODELS.includes(a))]);
      }
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

  const handleClassifierModelChange = (model: string) => {
    setSettings((prev) => ({ ...prev, AGY_AUTO_CLASSIFIER_MODEL: model, AGY_AUTO_CLASSIFIER_EFFORT: 'low' }));
  };

  const handleAliasChange = (index: number, field: 'alias' | 'target', value: string) => {
    setAliases((prev) => {
      const copy = [...prev];
      const current = copy[index];
      if (field === 'target') {
        const aliasNames = new Set(prev.map((r) => r.alias.trim()).filter(Boolean));
        const backendSlugs = availableModels.filter((id) => !aliasNames.has(id));
        const previousAlias = current.alias.trim();
        const shouldAutofillAlias =
          !previousAlias || previousAlias === current.target.trim() || backendSlugs.includes(previousAlias);
        copy[index] = {
          alias: shouldAutofillAlias ? value : current.alias,
          target: value,
        };
      } else {
        copy[index] = { ...current, [field]: value };
      }
      setSettings((s) => ({ ...s, AGY_MODEL_ALIASES: serializeAliases(copy) }));
      return copy;
    });
  };

  const handleAddAlias = () => {
    setAliases((prev) => {
      const updated = [...prev, { alias: '', target: '' }];
      setSettings((s) => ({ ...s, AGY_MODEL_ALIASES: serializeAliases(updated) }));
      return updated;
    });
  };

  const handleRemoveAlias = (index: number) => {
    setAliases((prev) => {
      const updated = prev.filter((_, i) => i !== index);
      setSettings((s) => ({ ...s, AGY_MODEL_ALIASES: serializeAliases(updated) }));
      return updated;
    });
  };

  const handleSave = async () => {
    const thoughtWrappers = parseThoughtTemplate(thoughtTemplate);
    if (!thoughtWrappers) {
      setStatusMsg({ type: 'error', text: 'Шаблон рассуждений должен содержать ровно один маркер {...}' });
      return;
    }
    setSaving(true);
    setStatusMsg(null);
    try {
      const payload = {
        ...settings,
        AGY_MODEL_ALIASES: serializeAliases(aliases),
        AGY_THOUGHT_TEXT_PREFIX: thoughtWrappers.prefix,
        AGY_THOUGHT_TEXT_SUFFIX: thoughtWrappers.suffix,
        AGY_AUTO_CLASSIFIER_EFFORT: settings.AGY_AUTO_CLASSIFIER_MODEL && settings.AGY_AUTO_CLASSIFIER_MODEL !== 'skip' ? 'low' : settings.AGY_AUTO_CLASSIFIER_EFFORT || 'low',
      };
      const res = await fetch(apiUrl('/v1/settings'), {
        method: 'PUT',
        headers: authHeaders,
        body: JSON.stringify({ settings: payload }),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Ошибка сохранения настроек');
      }
      setSettings(payload);
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
    <div className="flex-1 p-6 md:p-8 overflow-auto">
      <div className="max-w-6xl mx-auto w-full space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2.5">
              <SettingsIcon className="w-6 h-6 text-primary" />
              Настройки
            </h1>
            <p className="text-sm text-muted-foreground mt-1">
              Управление параметрами окружения и переключателями в реальном времени.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={loadSettings} disabled={loading} className="gap-1.5 cursor-pointer">
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              Обновить
            </Button>
            <Button
              size="sm"
              onClick={handleSave}
              disabled={saving || !parseThoughtTemplate(thoughtTemplate)}
              className="gap-1.5 shadow-sm cursor-pointer"
            >
              <Save className="w-4 h-4" />
              {saving ? 'Сохранение...' : 'Сохранить изменения'}
            </Button>
          </div>
        </div>

      {statusMsg && (
        <div
          className={`p-3.5 rounded-xl text-sm flex items-center gap-2.5 mb-6 transition-all ${
            statusMsg.type === 'success'
              ? 'bg-green-500/10 text-green-700 dark:text-green-300 border border-green-500/20'
              : 'bg-destructive/10 text-destructive border border-destructive/20'
          }`}
        >
          {statusMsg.type === 'success' ? (
            <CheckCircle2 className="w-4 h-4 shrink-0 text-green-600 dark:text-green-400" />
          ) : (
            <AlertCircle className="w-4 h-4 shrink-0 text-destructive" />
          )}
          <span>{statusMsg.text}</span>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Group 1: Transport & Models */}
        <div className="border border-border/70 rounded-xl p-5 bg-card dark:border-border/50 dark:bg-zinc-950/40 shadow-xs space-y-4">
          <div className="flex items-center gap-2 border-b border-border/60 pb-3">
            <Cpu className="w-4 h-4 text-primary" />
            <h2 className="text-xs font-semibold tracking-wider uppercase text-muted-foreground">
              Транспорт и Модели
            </h2>
          </div>
          <div>
            <label className="text-xs font-medium text-foreground/90">AGY_TRANSPORT (http / warm / cli)</label>
            <Input
              value={settings.AGY_TRANSPORT || ''}
              onChange={(e) => handleChange('AGY_TRANSPORT', e.target.value)}
              placeholder="http"
              className="mt-1.5 font-mono text-sm"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-foreground/90">AGY_FORCE_MODEL (Принудительная модель)</label>
            <Input
              value={settings.AGY_FORCE_MODEL || ''}
              onChange={(e) => handleChange('AGY_FORCE_MODEL', e.target.value)}
              placeholder="max-gem"
              className="mt-1.5 font-mono text-sm"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-foreground/90">AGY_WARM_IDLE_TIMEOUT_SECONDS</label>
            <Input
              value={settings.AGY_WARM_IDLE_TIMEOUT_SECONDS || ''}
              onChange={(e) => handleChange('AGY_WARM_IDLE_TIMEOUT_SECONDS', e.target.value)}
              placeholder="600"
              className="mt-1.5 font-mono text-sm"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-foreground/90">AGY_WARM_MAX_SESSIONS</label>
            <Input
              value={settings.AGY_WARM_MAX_SESSIONS || ''}
              onChange={(e) => handleChange('AGY_WARM_MAX_SESSIONS', e.target.value)}
              placeholder="20"
              className="mt-1.5 font-mono text-sm"
            />
          </div>
        </div>

        {/* Group 2: Account Pool */}
        <div className="border border-border/70 rounded-xl p-5 bg-card dark:border-border/50 dark:bg-zinc-950/40 shadow-xs space-y-4">
          <div className="flex items-center gap-2 border-b border-border/60 pb-3">
            <Users className="w-4 h-4 text-primary" />
            <h2 className="text-xs font-semibold tracking-wider uppercase text-muted-foreground">
              Пул Аккаунтов (Account Pool)
            </h2>
          </div>
          <SettingToggleRow
            title="AGY_POOL_ENABLED"
            description="Использовать пул аккаунтов для ротации"
            checked={!!settings.AGY_POOL_ENABLED}
            onCheckedChange={() => handleToggle('AGY_POOL_ENABLED')}
          />
          <div>
            <label className="text-xs font-medium text-foreground/90">AGY_POOL_COOLDOWN_SECONDS (Кулдаун при 429)</label>
            <Input
              value={settings.AGY_POOL_COOLDOWN_SECONDS || ''}
              onChange={(e) => handleChange('AGY_POOL_COOLDOWN_SECONDS', e.target.value)}
              placeholder="3600"
              className="mt-1.5 font-mono text-sm"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-foreground/90">AGY_POOL_MAX_RETRIES</label>
            <Input
              value={settings.AGY_POOL_MAX_RETRIES || ''}
              onChange={(e) => handleChange('AGY_POOL_MAX_RETRIES', e.target.value)}
              placeholder="3"
              className="mt-1.5 font-mono text-sm"
            />
          </div>
        </div>

        {/* Group 3: HTTP, Tools & Response Tuning */}
        <div className="border border-border/70 rounded-xl p-5 bg-card dark:border-border/50 dark:bg-zinc-950/40 shadow-xs space-y-3.5">
          <div className="flex items-center gap-2 border-b border-border/60 pb-3">
            <Sliders className="w-4 h-4 text-primary" />
            <h2 className="text-xs font-semibold tracking-wider uppercase text-muted-foreground">
              HTTP и Форматирование
            </h2>
          </div>

          <SettingToggleRow
            title="AGY_THOUGHT_AS_TEXT"
            description="Выводить рассуждения (thinking) в текст"
            checked={!!settings.AGY_THOUGHT_AS_TEXT}
            onCheckedChange={() => handleToggle('AGY_THOUGHT_AS_TEXT')}
          />

          <div className="p-3 rounded-lg border border-border/50 bg-muted/10 dark:bg-black/20 space-y-1.5">
            <label className="text-xs font-medium text-foreground/90">Шаблон блока рассуждений</label>
            <Input
              value={thoughtTemplate}
              onChange={(e) => setThoughtTemplate(e.target.value)}
              className="font-mono text-sm"
              aria-invalid={!parseThoughtTemplate(thoughtTemplate)}
            />
            <div className="text-[11px] text-muted-foreground">
              Маркер {'{...}'} обязателен и обозначает текст рассуждений. Перенос строки: \\n
            </div>
            {!parseThoughtTemplate(thoughtTemplate) && (
              <div className="text-[11px] text-destructive font-medium">
                Нужен ровно один неизменённый маркер {'{...}'}
              </div>
            )}
          </div>

          <SettingToggleRow
            title="AGY_HTTP_TRIM_TOOL_RESULTS"
            description="Обрезать большие результаты инструментов"
            checked={!!settings.AGY_HTTP_TRIM_TOOL_RESULTS}
            onCheckedChange={() => handleToggle('AGY_HTTP_TRIM_TOOL_RESULTS')}
          />

          <SettingToggleRow
            title="AGY_HTTP_EMPTY_AS_EMPTY_CONTENT"
            description="Возвращать пустой ответ вместо ошибки STOP"
            checked={!!settings.AGY_HTTP_EMPTY_AS_EMPTY_CONTENT}
            onCheckedChange={() => handleToggle('AGY_HTTP_EMPTY_AS_EMPTY_CONTENT')}
          />

          <div className="p-3 rounded-lg border border-border/50 bg-muted/10 dark:bg-black/20 space-y-2">
            <div><div className="text-sm font-medium leading-none">AGY_AUTO_CLASSIFIER_MODEL</div><div className="text-xs text-muted-foreground mt-1 leading-snug">Модель для авто-классификатора</div></div>
            <Select value={settings.AGY_AUTO_CLASSIFIER_MODEL || 'skip'} onChange={(e) => handleClassifierModelChange(e.target.value)}>
              <option value="skip">Разрешить всё (skip)</option>
              <option value="gemini-3.8-flash">Gemini 3.8 Flash</option>
              <option value="gemini-3.7-flash">Gemini 3.7 Flash</option>
              <option value="gemini-3.6-flash">Gemini 3.6 Flash</option>
              <option value="claude-sonnet-4-6">Claude Sonnet 4.6</option>
              <option value="claude-opus-4-6-thinking">Claude Opus 4.6 Thinking</option>
              <option value="gemini-pro-agent">Gemini Pro Agent</option>
              <option value="gpt-oss-120b-medium">GPT-OSS 120B</option>
            </Select>
          </div>

          <SettingToggleRow
            title="AGY_HTTP_DEBUG"
            description="Подробное логирование HTTP запросов"
            checked={!!settings.AGY_HTTP_DEBUG}
            onCheckedChange={() => handleToggle('AGY_HTTP_DEBUG')}
          />
        </div>

        {/* Group 4: Proxy & OAuth */}
        <div className="border border-border/70 rounded-xl p-5 bg-card dark:border-border/50 dark:bg-zinc-950/40 shadow-xs space-y-3.5">
          <div className="flex items-center gap-2 border-b border-border/60 pb-3">
            <ShieldCheck className="w-4 h-4 text-primary" />
            <h2 className="text-xs font-semibold tracking-wider uppercase text-muted-foreground">
              Прокси и OAuth
            </h2>
          </div>
          <div>
            <label className="text-xs font-medium text-foreground/90">AGY_GOOGLE_PROXY (Глобальный прокси)</label>
            <Input
              value={settings.AGY_GOOGLE_PROXY || ''}
              onChange={(e) => handleChange('AGY_GOOGLE_PROXY', e.target.value)}
              placeholder="http://user:pass@host:port"
              className="mt-1.5 font-mono text-sm"
            />
          </div>

          <SettingToggleRow
            title="AGY_OAUTH_REFRESH_ENABLED"
            description="Автоматический рефреш OAuth токенов"
            checked={!!settings.AGY_OAUTH_REFRESH_ENABLED}
            onCheckedChange={() => handleToggle('AGY_OAUTH_REFRESH_ENABLED')}
          />

          <SettingToggleRow
            title="AGY_SSL_VERIFY"
            description="Проверка SSL сертификатов (выключите для HTTP Toolkit)"
            checked={!!settings.AGY_SSL_VERIFY}
            onCheckedChange={() => handleToggle('AGY_SSL_VERIFY')}
          />

          <div>
            <label className="text-xs font-medium text-foreground/90">AGY_OAUTH_REFRESH_SKEW_SECONDS</label>
            <Input
              value={settings.AGY_OAUTH_REFRESH_SKEW_SECONDS || ''}
              onChange={(e) => handleChange('AGY_OAUTH_REFRESH_SKEW_SECONDS', e.target.value)}
              placeholder="120"
              className="mt-1.5 font-mono text-sm"
            />
          </div>
        </div>

        {/* Group 5: Custom Model Aliases */}
        <div className="border border-border/70 rounded-xl p-5 bg-card dark:border-border/50 dark:bg-zinc-950/40 shadow-xs space-y-4 md:col-span-2">
          <div className="flex items-center justify-between border-b border-border/60 pb-3">
            <div className="flex items-center gap-2">
              <Layers className="w-4 h-4 text-primary" />
              <div>
                <h2 className="text-xs font-semibold tracking-wider uppercase text-muted-foreground">
                  Собственные алиасы моделей
                </h2>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Задайте псевдоним (алиас), по которому клиенты могут обращаться к целевой модели бэкенда.
                </p>
              </div>
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleAddAlias}
              className="gap-1.5 text-xs h-8"
            >
              <Plus className="w-3.5 h-3.5" />
              Добавить алиас
            </Button>
          </div>

          {aliases.length === 0 ? (
            <div className="text-center py-6 text-xs text-muted-foreground border border-dashed border-border/70 rounded-lg">
              Пользовательские алиасы не настроены. Нажмите «Добавить алиас» выше.
            </div>
          ) : (
            <div className="space-y-2.5">
              <div className="grid grid-cols-12 gap-2.5 text-xs font-medium text-muted-foreground px-1">
                <div className="col-span-5">Алиас (что шлёт клиент)</div>
                <div className="col-span-6">Целевая модель бэкенда</div>
                <div className="col-span-1 text-right">Удалить</div>
              </div>
              {aliases.map((row, idx) => (
                <div key={idx} className="grid grid-cols-12 gap-2.5 items-center">
                  <div className="col-span-5">
                    <Input
                      value={row.alias}
                      onChange={(e) => handleAliasChange(idx, 'alias', e.target.value)}
                      placeholder="e.g. gpt-4o, my-model"
                      className="font-mono text-xs"
                    />
                  </div>
                  <div className="col-span-6">
                    <Select
                      value={row.target}
                      onChange={(e) => handleAliasChange(idx, 'target', e.target.value)}
                      className="font-mono text-xs"
                    >
                      <option value="">Выберите модель...</option>
                      {availableModels.map((mId) => (
                        <option key={mId} value={mId}>
                          {mId}
                        </option>
                      ))}
                      {row.target && !availableModels.includes(row.target) && (
                        <option value={row.target}>{row.target} (кастомная)</option>
                      )}
                    </Select>
                  </div>
                  <div className="col-span-1 flex justify-end">
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => handleRemoveAlias(idx)}
                      className="h-8 w-8 p-0 text-muted-foreground hover:text-destructive hover:bg-destructive/10"
                      title="Удалить"
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  </div>
  );
}
