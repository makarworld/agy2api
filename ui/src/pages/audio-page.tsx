import { useState, useEffect } from 'react';

export function AudioPage() {
  const [text, setText] = useState('Hello world!');
  const [voice, setVoice] = useState('alloy');
  const [voices, setVoices] = useState<any[]>([]);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [loadingTTS, setLoadingTTS] = useState(false);

  useEffect(() => {
    fetch('/v1/audio/voices', { headers: { Authorization: `Bearer ${localStorage.getItem('agy_api_key')}` } })
      .then(res => res.json())
      .then(data => {
        if (data.voices) setVoices(data.voices);
      })
      .catch(err => console.error(err));
  }, []);

  const handleTTS = async () => {
    setLoadingTTS(true);
    try {
      const apiKey = localStorage.getItem('agy_api_key') || '';
      const res = await fetch('/v1/audio/speech', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${apiKey}`
        },
        body: JSON.stringify({ model: 'tts-1', input: text, voice })
      });
      if (res.ok) {
        const blob = await res.blob();
        setAudioUrl(URL.createObjectURL(blob));
      } else {
        alert('Error generating audio');
      }
    } finally {
      setLoadingTTS(false);
    }
  };

  return (
    <div className="flex-1 overflow-auto p-6 space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight mb-2">Audio Playground</h1>
        <p className="text-muted-foreground">Test Text-to-Speech capabilities.</p>
      </div>

      <div className="max-w-2xl border border-border rounded-lg p-6 space-y-4">
        <h2 className="text-xl font-semibold">Text-to-Speech</h2>
        <div className="space-y-2">
          <label className="text-sm font-medium">Text</label>
          <textarea 
            className="w-full min-h-[100px] p-3 rounded-md border border-input bg-transparent"
            value={text} 
            onChange={e => setText(e.target.value)} 
          />
        </div>
        <div className="space-y-2">
          <label className="text-sm font-medium">Voice</label>
          <select 
            className="w-full p-2 rounded-md border border-input bg-transparent"
            value={voice} 
            onChange={e => setVoice(e.target.value)}
          >
            <option value="alloy">alloy (OpenAI Default)</option>
            {voices.map(v => (
              <option key={v.voice_type} value={v.voice_type}>{v.display_name} ({v.lang})</option>
            ))}
          </select>
        </div>
        <button 
          onClick={handleTTS} 
          disabled={loadingTTS}
          className="px-4 py-2 bg-primary text-primary-foreground rounded-md disabled:opacity-50"
        >
          {loadingTTS ? 'Generating...' : 'Generate Audio'}
        </button>
        
        {audioUrl && (
          <div className="mt-4 pt-4 border-t border-border">
            <audio src={audioUrl} controls autoPlay className="w-full" />
          </div>
        )}
      </div>
    </div>
  );
}
