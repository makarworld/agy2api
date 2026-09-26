import { useState, useEffect } from 'react';
import { apiUrl } from '../lib/api';
import { Button } from '../components/ui/button';
import { Select } from '../components/ui/select';
import { Mic, Volume2, Loader2 } from 'lucide-react';

export function AudioPage() {
  const [text, setText] = useState('Привет! Это проверка синтеза речи через локальный сервис AGY2API.');
  const [voice, setVoice] = useState('alloy');
  const [voices, setVoices] = useState<any[]>([]);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [loadingTTS, setLoadingTTS] = useState(false);

  const getApiKey = () => localStorage.getItem('AGY_API_KEY') || localStorage.getItem('agy_api_key') || '';

  useEffect(() => {
    fetch(apiUrl('/v1/audio/voices'), { headers: { Authorization: `Bearer ${getApiKey()}` } })
      .then((res) => res.json())
      .then((data) => {
        if (data.voices) setVoices(data.voices);
      })
      .catch((err) => console.error(err));
  }, []);

  const handleTTS = async () => {
    if (!text.trim()) return;
    setLoadingTTS(true);
    try {
      const apiKey = getApiKey();
      const res = await fetch(apiUrl('/v1/audio/speech'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${apiKey}`,
        },
        body: JSON.stringify({ model: 'tts-1', input: text, voice }),
      });
      if (res.ok) {
        const blob = await res.blob();
        setAudioUrl(URL.createObjectURL(blob));
      } else {
        alert('Ошибка генерации аудиопотока');
      }
    } finally {
      setLoadingTTS(false);
    }
  };

  return (
    <div className="flex-1 p-6 md:p-8 overflow-auto">
      <div className="max-w-6xl mx-auto w-full space-y-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2.5">
            <Mic className="w-6 h-6 text-primary" />
            Audio Playground
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Тестирование Text-to-Speech (TTS) и доступных голосов озвучки.
          </p>
        </div>

        <div className="max-w-2xl border border-border/80 rounded-xl p-6 space-y-5 bg-card shadow-xs">
          <div className="flex items-center gap-2 border-b border-border/60 pb-3">
            <Volume2 className="w-4 h-4 text-primary" />
            <h2 className="text-xs font-semibold tracking-wider uppercase text-muted-foreground">
              Синтез речи (Text-to-Speech)
            </h2>
          </div>

          <div className="space-y-2">
            <label className="text-xs font-medium text-foreground/90 uppercase tracking-wider">
              Текст для озвучивания
            </label>
            <textarea
              rows={4}
              className="w-full p-3 rounded-lg border border-border/80 bg-muted/30 hover:border-zinc-500/40 focus:border-primary focus:ring-2 focus:ring-primary/20 outline-none transition-all text-sm shadow-xs resize-none"
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Введите текст..."
            />
          </div>

          <div className="space-y-2">
            <label className="text-xs font-medium text-foreground/90 uppercase tracking-wider">
              Голос
            </label>
            <Select value={voice} onChange={(e) => setVoice(e.target.value)} className="h-10 text-sm">
              <option value="alloy">alloy (OpenAI Default)</option>
              {voices.map((v) => (
                <option key={v.voice_type} value={v.voice_type}>
                  {v.display_name} ({v.lang})
                </option>
              ))}
            </Select>
          </div>

          <Button onClick={handleTTS} disabled={loadingTTS || !text.trim()} className="gap-2 cursor-pointer shadow-xs">
            {loadingTTS ? <Loader2 className="w-4 h-4 animate-spin" /> : <Volume2 className="w-4 h-4" />}
            {loadingTTS ? 'Генерация аудио…' : 'Синтезировать речь'}
          </Button>

          {audioUrl && (
            <div className="pt-4 border-t border-border/60 space-y-2">
              <span className="text-xs text-muted-foreground font-medium">Результат генерации:</span>
              <audio controls src={audioUrl} className="w-full rounded-lg" autoPlay />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
