import { useEffect } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Layout } from './components/layout';
import { ApiKeysPage } from './pages/api-keys-page';
import { LogsPage } from './pages/logs-page';
import { ChatPage } from './pages/chat-page';

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
          <Route path="logs" element={<LogsPage />} />
          <Route path="keys" element={<ApiKeysPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
