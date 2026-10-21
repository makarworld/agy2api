import { useState, useEffect, useCallback } from 'react';

const STORAGE_KEYS = ['AGY_API_KEY', 'agy_api_key'];

function getStoredKey(): string {
  for (const k of STORAGE_KEYS) {
    const val = localStorage.getItem(k);
    if (val && val.trim()) {
      return val.trim();
    }
  }
  return '';
}

export function useApiKey() {
  const [apiKey, setApiKey] = useState<string>(getStoredKey);

  useEffect(() => {
    const handleUpdate = () => {
      setApiKey(getStoredKey());
    };
    window.addEventListener('storage', handleUpdate);
    window.addEventListener('agy:auth-change', handleUpdate);
    return () => {
      window.removeEventListener('storage', handleUpdate);
      window.removeEventListener('agy:auth-change', handleUpdate);
    };
  }, []);

  const saveApiKey = useCallback((key: string) => {
    const clean = key.trim();
    if (clean) {
      localStorage.setItem('AGY_API_KEY', clean);
      localStorage.setItem('agy_api_key', clean);
    } else {
      localStorage.removeItem('AGY_API_KEY');
      localStorage.removeItem('agy_api_key');
    }
    setApiKey(clean);
    window.dispatchEvent(new CustomEvent('agy:auth-change'));
  }, []);

  const clearApiKey = useCallback(() => {
    localStorage.removeItem('AGY_API_KEY');
    localStorage.removeItem('agy_api_key');
    setApiKey('');
    window.dispatchEvent(new CustomEvent('agy:auth-change'));
  }, []);

  return { apiKey, saveApiKey, clearApiKey };
}
