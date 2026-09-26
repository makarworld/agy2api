import { useState, useEffect } from 'react';

export function useApiKey() {
  const [apiKey, setApiKey] = useState<string>(() => {
    return localStorage.getItem('AGY_API_KEY') || localStorage.getItem('agy_api_key') || 'agy-secret-key-12345';
  });

  useEffect(() => {
    const key = localStorage.getItem('AGY_API_KEY') || localStorage.getItem('agy_api_key') || 'agy-secret-key-12345';
    setApiKey(key);
  }, []);

  const saveApiKey = (key: string) => {
    localStorage.setItem('AGY_API_KEY', key);
    localStorage.setItem('agy_api_key', key);
    setApiKey(key);
  };

  const clearApiKey = () => {
    localStorage.removeItem('AGY_API_KEY');
    localStorage.removeItem('agy_api_key');
    setApiKey('');
  };

  return { apiKey, saveApiKey, clearApiKey };
}
