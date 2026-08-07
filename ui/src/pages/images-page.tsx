import { useState } from 'react';
import { useApiKey } from '../hooks/use-api-key';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Image as ImageIcon, Loader2 } from 'lucide-react';

export function ImagesPage() {
  const { apiKey } = useApiKey();
  const [prompt, setPrompt] = useState('');
  const [images, setImages] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim()) return;
    if (!apiKey) {
      alert("Please set your API key in the Keys page first.");
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch('/v1/images/generations', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${apiKey}`
        },
        body: JSON.stringify({
          prompt: prompt,
          n: 1,
          response_format: "url"
        })
      });

      if (!response.ok) {
        throw new Error(`API Error: ${response.status} ${response.statusText}`);
      }

      const data = await response.json();
      if (data.data && data.data.length > 0) {
        // We get back either url or b64_json
        const newImages = data.data.map((img: any) => img.url || `data:image/png;base64,${img.b64_json}`);
        setImages(prev => [...newImages, ...prev]);
      }
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full bg-background p-8 overflow-auto">
      <div className="max-w-4xl mx-auto w-full space-y-8">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Generate Images</h1>
          <p className="text-sm text-muted-foreground mt-2">
            Test the /v1/images/generations endpoint.
          </p>
        </div>

        <form onSubmit={handleGenerate} className="flex gap-4 items-end">
          <div className="flex-1 space-y-2">
            <label className="text-sm font-medium">Prompt</label>
            <Input
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Describe the image you want to generate..."
              disabled={isLoading}
            />
          </div>
          <Button type="submit" disabled={isLoading || !prompt.trim()} className="gap-2">
            {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <ImageIcon className="w-4 h-4" />}
            Generate
          </Button>
        </form>

        {error && (
          <div className="p-4 bg-destructive/10 text-destructive rounded-xl text-sm">
            {error}
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-8">
          {images.map((img, i) => (
            <div key={i} className="border rounded-2xl overflow-hidden bg-card shadow-sm group relative flex justify-center bg-black/5">
              <img src={img} alt="Generated" className="w-full h-auto object-contain" />
            </div>
          ))}
          {images.length === 0 && !isLoading && !error && (
             <div className="col-span-full py-20 text-center text-muted-foreground border-2 border-dashed rounded-2xl">
               No images generated yet.
             </div>
          )}
        </div>
      </div>
    </div>
  );
}
