import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';

export type Language = 'ru' | 'en';

export const translations = {
  ru: {
    // Top Bar & Common
    serviceActive: 'Сервис активен',
    version: 'v1.0',
    logout: 'Выйти из сессии',
    logoutConfirm: 'Выйти из панели управления?',
    copied: 'Скопировано',
    copy: 'Копировать',
    refresh: 'Обновить',
    save: 'Сохранить',
    delete: 'Удалить',
    cancel: 'Отмена',
    loading: 'Загрузка...',
    actions: 'Действия',
    status: 'Статус',
    active: 'Активен',
    inactive: 'Неактивен',
    error: 'Ошибка',
    success: 'Успешно',
    checkAgain: 'Проверить снова',

    // Sidebar Navigation
    navQuickstart: 'Быстрый старт',
    navPlayground: 'Playground',
    navChat: 'Чат',
    navImages: 'Картинки',
    navAudio: 'Аудио',
    navMonitoring: 'Мониторинг',
    navRequests: 'Запросы',
    navStats: 'Статистика',
    navLogs: 'Системные логи',
    navConfiguration: 'Конфигурация',
    navPool: 'Пул аккаунтов',
    navSettings: 'Настройки',
    navKeys: 'API Ключи',

    // Quickstart Page
    qsBadge: 'Быстрый старт',
    qsTitle: 'Начало работы с AGY2API',
    qsSubtitle: 'Выполните 3 простых шага, чтобы подключить подписку Gemini, протестировать стриминг в чате и запустить Claude Code через настроенный bat-файл.',
    qsStep1Title: 'Добавьте Google-аккаунт с подпиской в пул',
    qsStep1Desc: 'Для работы сервиса требуется хотя бы один авторизованный аккаунт Google. Нажмите кнопку перехода в пул, нажмите «Сгенерировать ссылку входа» (Generate Login Link), перейдите по ней в браузере («Открыть вход Google») и авторизуйтесь в аккаунт с активной подпиской. Полученный код авторизации (или redirect URL) вставьте в поле и нажмите кнопку «Подключить аккаунт» (Connect Account).',
    qsStep1Button: 'Перейти в пул аккаунтов',
    qsAccountsInPool: 'Аккаунтов в пуле: ',
    qsNoAccounts: 'Нет аккаунтов',
    qsStep2Title: 'Сделайте первый тестовый запрос в чате Playground',
    qsStep2Desc: 'Убедитесь, что стриминг и генерация работают стабильно. Модель по умолчанию выставлена в max-gem (быстрый стриминг с рассуждениями). Отправьте текстовое сообщение или прикрепите изображение для анализа.',
    qsStep2Button: 'Открыть чат Playground',
    qsStep3Title: 'Откройте Claude CLI с моделью max-gem',
    qsStep3Desc: 'Запускайте официальный Claude Code через сгенерированный gclaude.bat в папке User/bin. Все переменные окружения и модель выставляются локально без изменения системного файла settings.json.',
    qsCliInstalled: 'Claude CLI установлен',
    qsCliNotFound: 'CLI не найден',
    qsCheckingCli: 'Проверка установки Claude CLI...',
    qsInstallGuideTitle: 'Установите Claude Code CLI (из официальной документации Anthropic):',
    qsModelLabel: 'Модель:',
    qsLaunchButton: 'Запустить Claude Code',
    qsUpdateButton: 'Обновить gclaude.bat',

    // Pool Page
    poolTitle: 'Пул аккаунтов',
    poolSubtitle: 'Google Antigravity аккаунты, подключенные для автоматической ротации и распределения квот.',
    poolRefreshQuotas: 'Обновить квоты',
    poolRefreshQuotasTitle: 'Принудительно запросить у Google API актуальные лимиты квот для всех аккаунтов',
    poolAddTitle: 'Добавить аккаунт через Google OAuth',
    poolLabelField: 'Метка аккаунта (опционально)',
    poolLabelPlaceholder: 'например: личный, рабочий-2',
    poolProxyField: 'Прокси (опционально)',
    poolGenerateBtn: 'Сгенерировать ссылку входа',
    poolRegenerateBtn: 'Сгенерировать заново',
    poolGenerating: 'Генерация...',
    poolOpenGoogle: 'Открыть вход Google',
    poolCopyLink: 'Скопировать ссылку',
    poolAuthCodeLabel: 'Вставьте код авторизации или Redirect URL:',
    poolAuthCodePlaceholder: '4/0ATsMZq... или https://antigravity.google/oauth-callback?code=...',
    poolConnectBtn: 'Подключить аккаунт',
    poolConnecting: 'Подключение...',
    poolConnectedSuccess: 'Аккаунт успешно подключен!',
    poolQuotasRefreshed: 'Квоты всех аккаунтов успешно обновлены.',

    // Accounts Table
    tableAccount: 'Аккаунт',
    tableStatus: 'Статус',
    tableGeminiQuota: 'Квоты Gemini',
    tableClaudeQuota: 'Квоты Claude',
    tableProxy: 'Прокси',
    tableActions: 'Действия',
    tableHealthy: 'Здоров',
    tableCooldown: 'Кулдаун',
    tableRateLimited: 'Лимит',
    tableUnhealthy: 'Ошибка',
    tableActiveNow: 'Активен сейчас',
    tableRelogin: 'Перепривязать',
    tableHealthcheck: 'Проверить квоты',
    tableDelete: 'Удалить аккаунт',
    tableDeleteConfirm: 'Удалить этот аккаунт из пула?',
    tableNoAccounts: 'Нет подключенных аккаунтов. Добавьте первый аккаунт выше.',

    // Chat Page
    chatPlaceholder: 'Напишите сообщение...',
    chatSend: 'Отправить',
    chatClear: 'Очистить историю',
    chatClearConfirm: 'Очистить историю сообщений?',
    chatSelectModel: 'Модель:',
    chatAttachImage: 'Прикрепить изображение',
    chatThinking: 'Думает...',
    chatEmptyTitle: 'AGY2API Chat Playground',
    chatEmptyDesc: 'Отправляйте запросы моделям Gemini и Claude с поддержкой мыслей <think> и изображений.',

    // Images Page
    imagesTitle: 'Генерация изображений',
    imagesSubtitle: 'Генерация изображений через Cloud Code Assist модели Imagen.',
    imagesPromptPlaceholder: 'Опишите изображение на английском или русском языке...',
    imagesGenerateBtn: 'Сгенерировать изображение',
    imagesGenerating: 'Генерация...',
    imagesSizeLabel: 'Соотношение сторон:',
    imagesRecentTitle: 'Сгенерированные изображения',
    imagesDownload: 'Скачать',

    // Audio Page
    audioTitle: 'Озвучка текста (TTS)',
    audioSubtitle: 'Преобразование текста в речь через сервис CapCut/TTS.',
    audioTextPlaceholder: 'Введите текст для озвучки...',
    audioVoiceLabel: 'Голос:',
    audioGenerateBtn: 'Озвучить текст',
    audioGenerating: 'Озвучивание...',

    // Requests Page
    requestsTitle: 'История запросов',
    requestsSubtitle: 'Лог последних обращений к API с детализацией токенов, задержек и статусов.',
    requestsSearchPlaceholder: 'Поиск по модели, аккаунту, тексту...',
    requestsAllStatuses: 'Все статусы',
    requestsSuccessOnly: 'Только успешные',
    requestsFailedOnly: 'Только ошибки',

    // Stats Page
    statsTitle: 'Статистика сервиса',
    statsSubtitle: 'Метрики активности, использования токенов, аптайма и потребления по моделям.',
    statsTotalRequests: 'Всего запросов',
    statsSuccessRate: 'Успешность',
    statsTotalTokens: 'Всего токенов',
    statsUptime: 'Время работы',

    // Settings Page
    settingsTitle: 'Настройки окружения',
    settingsSubtitle: 'Управление параметрами выполнения, пулом, лимитами и выводом рассуждений.',
    settingsSaveBtn: 'Сохранить настройки',
    settingsSaving: 'Сохранение...',
    settingsSavedSuccess: 'Настройки успешно сохранены!',

    // API Keys Page
    keysTitle: 'API Ключи',
    keysSubtitle: 'Управление мастер-ключами и создание пользовательских ключей с лимитами.',
    keysCreateTitle: 'Создать новый API-ключ',
    keysNamePlaceholder: 'Название ключа (например Cursor, Bob)',
    keysDaysPlaceholder: 'Срок действия в днях (0 = бессрочно)',
    keysLimitPlaceholder: 'Дневной лимит токенов (0 = без лимита)',
    keysCreateBtn: 'Создать ключ',

    // Auth Guard
    authModalTitle: 'Требуется авторизация',
    authModalDesc: 'Запросы возвращают 401. Введите пароль AGY_ADMIN_PASSWORD из .env',
    authInputPlaceholder: 'AGY_ADMIN_PASSWORD...',
    authSubmitBtn: 'Применить пароль',
    authLoginBtn: 'Войти',
    authInvalidPassword: 'Неверный пароль. Проверьте AGY_ADMIN_PASSWORD в файле .env',
  },
  en: {
    // Top Bar & Common
    serviceActive: 'Service Active',
    version: 'v1.0',
    logout: 'Log Out',
    logoutConfirm: 'Log out of admin session?',
    copied: 'Copied',
    copy: 'Copy',
    refresh: 'Refresh',
    save: 'Save',
    delete: 'Delete',
    cancel: 'Cancel',
    loading: 'Loading...',
    actions: 'Actions',
    status: 'Status',
    active: 'Active',
    inactive: 'Inactive',
    error: 'Error',
    success: 'Success',
    checkAgain: 'Check Again',

    // Sidebar Navigation
    navQuickstart: 'Quickstart',
    navPlayground: 'Playground',
    navChat: 'Chat',
    navImages: 'Images',
    navAudio: 'Audio',
    navMonitoring: 'Monitoring',
    navRequests: 'Requests',
    navStats: 'Stats',
    navLogs: 'System Logs',
    navConfiguration: 'Configuration',
    navPool: 'Account Pool',
    navSettings: 'Settings',
    navKeys: 'API Keys',

    // Quickstart Page
    qsBadge: 'Quickstart',
    qsTitle: 'Getting Started with AGY2API',
    qsSubtitle: 'Complete 3 simple steps to connect your Gemini subscription, test streaming in chat, and launch Claude Code via configured batch script.',
    qsStep1Title: 'Add a Google Account with Subscription to the Pool',
    qsStep1Desc: 'At least one authorized Google account is required. Click the button to go to the pool, click "Generate Login Link", open it in your browser ("Open Google Sign-In"), and log in with your subscribed Google account. Paste the authorization code (or redirect URL) and click "Connect Account".',
    qsStep1Button: 'Go to Account Pool',
    qsAccountsInPool: 'Accounts in pool: ',
    qsNoAccounts: 'No accounts',
    qsStep2Title: 'Send Your First Test Request in Playground Chat',
    qsStep2Desc: 'Verify that streaming and model generation work smoothly. Default model is set to max-gem (fast streaming with thinking). Send any text message or attach an image for analysis.',
    qsStep2Button: 'Open Playground Chat',
    qsStep3Title: 'Launch Claude CLI with max-gem Model',
    qsStep3Desc: 'Run official Claude Code through the generated gclaude.bat in User/bin. All environment variables and models are configured locally without modifying system settings.json.',
    qsCliInstalled: 'Claude CLI installed',
    qsCliNotFound: 'CLI not found',
    qsCheckingCli: 'Checking Claude CLI installation...',
    qsInstallGuideTitle: 'Install Claude Code CLI (from official Anthropic documentation):',
    qsModelLabel: 'Model:',
    qsLaunchButton: 'Launch Claude Code',
    qsUpdateButton: 'Update gclaude.bat',

    // Pool Page
    poolTitle: 'Account Pool',
    poolSubtitle: 'Google Antigravity accounts connected for automatic rotation and quota sharing.',
    poolRefreshQuotas: 'Refresh Quotas',
    poolRefreshQuotasTitle: 'Query Google API to refresh remaining quota limits for all accounts',
    poolAddTitle: 'Add Account via Google OAuth',
    poolLabelField: 'Account Label (optional)',
    poolLabelPlaceholder: 'e.g. personal, work-2',
    poolProxyField: 'Proxy (optional)',
    poolGenerateBtn: 'Generate Login Link',
    poolRegenerateBtn: 'Regenerate Link',
    poolGenerating: 'Generating...',
    poolOpenGoogle: 'Open Google Sign-In',
    poolCopyLink: 'Copy Link',
    poolAuthCodeLabel: 'Paste Authorization Code or Redirect URL:',
    poolAuthCodePlaceholder: '4/0ATsMZq... or https://antigravity.google/oauth-callback?code=...',
    poolConnectBtn: 'Connect Account',
    poolConnecting: 'Connecting...',
    poolConnectedSuccess: 'Account connected successfully!',
    poolQuotasRefreshed: 'Quotas refreshed successfully for all accounts.',

    // Accounts Table
    tableAccount: 'Account',
    tableStatus: 'Status',
    tableGeminiQuota: 'Gemini Quota',
    tableClaudeQuota: 'Claude Quota',
    tableProxy: 'Proxy',
    tableActions: 'Actions',
    tableHealthy: 'Healthy',
    tableCooldown: 'Cooldown',
    tableRateLimited: 'Rate Limited',
    tableUnhealthy: 'Unhealthy',
    tableActiveNow: 'Active Now',
    tableRelogin: 'Relogin',
    tableHealthcheck: 'Check Quota',
    tableDelete: 'Delete Account',
    tableDeleteConfirm: 'Delete this account from the pool?',
    tableNoAccounts: 'No connected accounts yet. Add your first account above.',

    // Chat Page
    chatPlaceholder: 'Type a message...',
    chatSend: 'Send',
    chatClear: 'Clear History',
    chatClearConfirm: 'Clear message history?',
    chatSelectModel: 'Model:',
    chatAttachImage: 'Attach image',
    chatThinking: 'Thinking...',
    chatEmptyTitle: 'AGY2API Chat Playground',
    chatEmptyDesc: 'Send requests to Gemini and Claude models with reasoning <think> and multimodal vision support.',

    // Images Page
    imagesTitle: 'Image Generation',
    imagesSubtitle: 'Generate images using Cloud Code Assist Imagen models.',
    imagesPromptPlaceholder: 'Describe the image prompt in English or Russian...',
    imagesGenerateBtn: 'Generate Image',
    imagesGenerating: 'Generating...',
    imagesSizeLabel: 'Aspect Ratio:',
    imagesRecentTitle: 'Generated Images',
    imagesDownload: 'Download',

    // Audio Page
    audioTitle: 'Text to Speech (TTS)',
    audioSubtitle: 'Convert text to speech via CapCut/TTS service.',
    audioTextPlaceholder: 'Enter text to synthesize...',
    audioVoiceLabel: 'Voice:',
    audioGenerateBtn: 'Generate Audio',
    audioGenerating: 'Generating...',

    // Requests Page
    requestsTitle: 'Request History',
    requestsSubtitle: 'Live log of API requests with token stats, latency, and response status.',
    requestsSearchPlaceholder: 'Search by model, account, text...',
    requestsAllStatuses: 'All statuses',
    requestsSuccessOnly: 'Success only',
    requestsFailedOnly: 'Failed only',

    // Stats Page
    statsTitle: 'Service Statistics',
    statsSubtitle: 'Activity metrics, token usage, uptime, and model breakdown.',
    statsTotalRequests: 'Total Requests',
    statsSuccessRate: 'Success Rate',
    statsTotalTokens: 'Total Tokens',
    statsUptime: 'Uptime',

    // Settings Page
    settingsTitle: 'Environment Settings',
    settingsSubtitle: 'Manage runtime parameters, pooling, limits, and thinking output.',
    settingsSaveBtn: 'Save Settings',
    settingsSaving: 'Saving...',
    settingsSavedSuccess: 'Settings saved successfully!',

    // API Keys Page
    keysTitle: 'API Keys',
    keysSubtitle: 'Manage master keys and create limited API keys with token quotas.',
    keysCreateTitle: 'Create New API Key',
    keysNamePlaceholder: 'Key Name (e.g. Cursor, Bob)',
    keysDaysPlaceholder: 'Expiration in days (0 = unlimited)',
    keysLimitPlaceholder: 'Daily output limit (0 = unlimited)',
    keysCreateBtn: 'Create Key',

    // Auth Guard
    authModalTitle: 'Authentication Required',
    authModalDesc: 'Requests returned 401. Enter AGY_ADMIN_PASSWORD from .env',
    authInputPlaceholder: 'AGY_ADMIN_PASSWORD...',
    authSubmitBtn: 'Apply Password',
    authLoginBtn: 'Log In',
    authInvalidPassword: 'Invalid password. Check AGY_ADMIN_PASSWORD in .env',
  },
};

interface I18nContextType {
  lang: Language;
  setLang: (lang: Language) => void;
  t: typeof translations['ru'];
}

const I18nContext = createContext<I18nContextType>({
  lang: 'ru',
  setLang: () => {},
  t: translations.ru,
});

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<Language>(() => {
    if (typeof window !== 'undefined') {
      const stored = localStorage.getItem('AGY_LANG');
      if (stored === 'en' || stored === 'ru') return stored;
    }
    return 'ru'; // Russian default
  });

  const setLang = useCallback((newLang: Language) => {
    setLangState(newLang);
    if (typeof window !== 'undefined') {
      localStorage.setItem('AGY_LANG', newLang);
      window.dispatchEvent(new CustomEvent('agy:lang-change', { detail: newLang }));
    }
  }, []);

  useEffect(() => {
    const handleStorage = () => {
      const stored = localStorage.getItem('AGY_LANG');
      if (stored === 'en' || stored === 'ru') {
        setLangState(stored);
      }
    };
    window.addEventListener('storage', handleStorage);
    return () => window.removeEventListener('storage', handleStorage);
  }, []);

  return (
    <I18nContext.Provider value={{ lang, setLang, t: translations[lang] }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n() {
  return useContext(I18nContext);
}
