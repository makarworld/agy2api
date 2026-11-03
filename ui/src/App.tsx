import { useEffect } from 'react';
import { HashRouter, Routes, Route } from 'react-router-dom';
import { I18nProvider } from './lib/i18n';
import { Layout } from './components/layout';
import { AuthGuard } from './components/auth-guard';
import { QuickstartPage } from './pages/quickstart-page';
import { ApiKeysPage } from './pages/api-keys-page';
import { LogsPage } from './pages/logs-page';
import { ChatPage } from './pages/chat-page';
import { ImagesPage } from './pages/images-page';
import { AudioPage } from './pages/audio-page';
import { StatsPage } from './pages/stats-page';
import { PoolPage } from './pages/pool-page';
import { RequestsPage } from './pages/requests-page';
import { SettingsPage } from './pages/settings-page';

function App() {
  // Apply dark mode based on preference or default
  useEffect(() => {
    document.documentElement.classList.add('dark');
  }, []);

  return (
    <I18nProvider>
      <HashRouter>
        <AuthGuard>
          <Routes>
            <Route path="/" element={<Layout />}>
              <Route index element={<QuickstartPage />} />
              <Route path="chat" element={<ChatPage />} />
              <Route path="images" element={<ImagesPage />} />
              <Route path="audio" element={<AudioPage />} />
              <Route path="requests" element={<RequestsPage />} />
              <Route path="stats" element={<StatsPage />} />
              <Route path="pool" element={<PoolPage />} />
              <Route path="settings" element={<SettingsPage />} />
              <Route path="logs" element={<LogsPage />} />
              <Route path="keys" element={<ApiKeysPage />} />
            </Route>
          </Routes>
        </AuthGuard>
      </HashRouter>
    </I18nProvider>
  );
}

export default App;
