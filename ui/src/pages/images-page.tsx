import { useState } from 'react';
import { useApiKey } from '../hooks/use-api-key';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Image as ImageIcon, Loader2, Download, Copy, Check, Eye, X } from 'lucide-react';
import { apiUrl } from '../lib/api';

export function ImagesPage() {
  const { apiKey } = useApiKey();
  const [prompt, setPrompt] = useState('');
  const [images, setImages] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null);
  const [previewImg, setPreviewImg] = useState<string | null>(null);

  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim()) return;
    if (!apiKey) {
      alert('Сначала укажите API-ключ в настройках.');
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch(apiUrl('/v1/images/generations'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${apiKey}`,
        },
        body: JSON.stringify({
          prompt: prompt,
          n: 1,
          response_format: 'url',
        }),
      });

      if (!response.ok) {
        const errJson = await response.json().catch(() => ({}));
        throw new Error(errJson.detail || `HTTP ${response.status} ${response.statusText}`);
      }

      const data = await response.json();
      if (data.data && data.data.length > 0) {
        const newImages = data.data.map((img: any) => img.url || `data:image/png;base64,${img.b64_json}`);
        setImages((prev) => [...newImages, ...prev]);
      }
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleCopyUrl = (url: string, idx: number) => {
    navigator.clipboard.writeText(url);
    setCopiedIdx(idx);
    setTimeout(() => setCopiedIdx(null), 2000);
  };

  const handleDownload = (url: string, idx: number) => {
    const a = document.createElement('a');
    a.href = url;
    a.download = `generated-image-${idx + 1}.png`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  return (
    <div className="flex-1 p-6 md:p-8 overflow-auto">
      <div className="max-w-6xl mx-auto w-full space-y-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2.5">
            <ImageIcon className="w-6 h-6 text-primary" />
            Image Generation
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Тестирование эндпоинта генерации изображений /v1/images/generations.
          </p>
        </div>

        {/* Prompt Input Card */}
        <div className="border border-border/80 rounded-xl p-5 bg-card shadow-xs space-y-3">
          <form onSubmit={handleGenerate} className="space-y-3">
            <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Промпт для генерации
            </label>
            <div className="flex gap-3">
              <Input
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder="Опишите изображение (e.g. futuristic cyberpunk city in neon lights, 4k)..."
                disabled={isLoading}
                className="h-10 text-sm"
              />
              <Button type="submit" disabled={isLoading || !prompt.trim()} className="h-10 gap-2 shrink-0 cursor-pointer">
                {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <ImageIcon className="w-4 h-4" />}
                <span>Сгенерировать</span>
              </Button>
            </div>
          </form>
        </div>

        {error && (
          <div className="p-4 bg-destructive/10 text-destructive border border-destructive/25 rounded-xl text-xs font-mono">
            {error}
          </div>
        )}

        {/* Gallery */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {images.map((img, i) => (
            <div
              key={i}
              className="border border-border/80 rounded-xl overflow-hidden bg-card shadow-xs group relative flex flex-col justify-between"
            >
              <div className="aspect-square w-full overflow-hidden bg-muted/20 relative flex items-center justify-center">
                <img src={img} alt={`Generated ${i + 1}`} className="w-full h-full object-cover" />
                <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setPreviewImg(img)}
                    className="h-8 w-8 p-0 rounded-lg bg-card/80 backdrop-blur-xs text-foreground hover:bg-card cursor-pointer"
                    title="Увеличить"
                  >
                    <Eye className="w-4 h-4" />
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => handleCopyUrl(img, i)}
                    className="h-8 w-8 p-0 rounded-lg bg-card/80 backdrop-blur-xs text-foreground hover:bg-card cursor-pointer"
                    title="Копировать URL"
                  >
                    {copiedIdx === i ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => handleDownload(img, i)}
                    className="h-8 w-8 p-0 rounded-lg bg-card/80 backdrop-blur-xs text-foreground hover:bg-card cursor-pointer"
                    title="Скачать файл"
                  >
                    <Download className="w-4 h-4" />
                  </Button>
                </div>
              </div>
            </div>
          ))}

          {images.length === 0 && !isLoading && !error && (
            <div className="col-span-full py-16 text-center text-muted-foreground border border-dashed border-border/70 rounded-xl flex flex-col items-center justify-center">
              <ImageIcon className="w-8 h-8 opacity-40 mb-2" />
              <span className="text-sm">Изображения пока не сгенерированы</span>
            </div>
          )}
        </div>
      </div>

      {/* Fullscreen Preview Modal */}
      {previewImg && (
        <div
          className="fixed inset-0 z-50 bg-black/80 backdrop-blur-xs flex items-center justify-center p-4 cursor-pointer"
          onClick={() => setPreviewImg(null)}
        >
          <div className="relative max-w-4xl max-h-[90vh]" onClick={(e) => e.stopPropagation()}>
            <img src={previewImg} alt="Preview" className="max-w-full max-h-[85vh] rounded-xl object-contain shadow-2xl border border-border/60" />
            <button
              onClick={() => setPreviewImg(null)}
              className="absolute -top-3 -right-3 p-1.5 rounded-full bg-card border border-border text-foreground hover:bg-muted transition-colors cursor-pointer shadow-md"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
