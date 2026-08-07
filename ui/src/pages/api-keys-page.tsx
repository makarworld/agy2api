import { useState, useEffect } from 'react';
import { useApiKey } from '../hooks/use-api-key';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Key } from 'lucide-react';

export function ApiKeysPage() {
  const { apiKey, saveApiKey } = useApiKey();
  const [inputValue, setInputValue] = useState(apiKey);
  const [saved, setSaved] = useState(false);

  // Sync state when apiKey loads from hook
  useEffect(() => {
    setInputValue(apiKey);
  }, [apiKey]);

  const handleSave = () => {
    saveApiKey(inputValue);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="flex-1 p-8 overflow-auto">
      <div className="max-w-2xl mx-auto space-y-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">API Keys</h1>
          <p className="text-sm text-muted-foreground mt-2">
            Configure your AGY2API secret key to access the backend endpoints.
          </p>
        </div>

        <div className="p-6 border rounded-xl bg-card text-card-foreground shadow-sm">
          <div className="space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-medium flex items-center gap-2">
                <Key className="w-4 h-4" />
                AGY_API_KEY
              </label>
              <Input
                type="password"
                placeholder="sk-..."
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                This key is stored locally in your browser and sent with every request.
              </p>
            </div>
            <Button onClick={handleSave} className="w-full sm:w-auto">
              {saved ? 'Saved!' : 'Save Key'}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
