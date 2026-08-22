import { useEffect } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Layout } from './components/layout';
import { ApiKeysPage } from './pages/api-keys-page';
import { LogsPage } from './pages/logs-page';
import { ChatPage } from './pages/chat-page';
import { ImagesPage } from './pages/images-page';
import { AudioPage } from './pages/audio-page';
import { StatsPage } from './pages/stats-page';
import { PoolPage } from './pages/pool-page';

function App() {
  // Apply dark mode based on preference or default
  useEffect(() => {
    document.documentElement.classList.add('dark');
  }, []);

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<ChatPage />} />
          <Route path="images" element={<ImagesPage />} />
          <Route path="audio" element={<AudioPage />} />
          <Route path="logs" element={<LogsPage />} />
          <Route path="stats" element={<StatsPage />} />
          <Route path="pool" element={<PoolPage />} />
          <Route path="keys" element={<ApiKeysPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
