import { useState, useEffect } from 'react';

export function useApiKey() {
  const [apiKey, setApiKey] = useState<string>('');

  useEffect(() => {
    const key = localStorage.getItem('AGY_API_KEY') || '';
    setApiKey(key);
  }, []);

  const saveApiKey = (key: string) => {
    localStorage.setItem('AGY_API_KEY', key);
    setApiKey(key);
  };

  return { apiKey, saveApiKey };
}
