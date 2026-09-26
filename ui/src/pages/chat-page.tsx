import React, { useState, useRef, useEffect } from 'react';
import { useApiKey } from '../hooks/use-api-key';
import { fileToBase64 } from '../lib/utils';
import { apiUrl } from '../lib/api';
import { Input } from '../components/ui/input';
import { Button } from '../components/ui/button';
import {
  Send,
  Image as ImageIcon,
  X,
  MessageSquare,
  Bot,
  User,
  Trash2,
  Copy,
  Check,
  Cpu,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';

type Message = {
  role: 'user' | 'assistant';
  content: any;
};

export function ChatPage() {
  const { apiKey } = useApiKey();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [attachedFiles, setAttachedFiles] = useState<{ file: File; url: string }[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [models, setModels] = useState<string[]>(['max-gem']);
  const [selectedModel, setSelectedModel] = useState('max-gem');
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  useEffect(() => {
    if (!apiKey) return;
    fetch(apiUrl('/v1/models'), {
      headers: { Authorization: `Bearer ${apiKey}` },
    })
      .then((r) => r.json())
      .then((d) => {
        const mList = (d.data || [])
          .map((m: any) => m.id)
          .filter((id: string) => id && !id.includes(' '));
        if (mList.length > 0) {
          setModels(mList);
          if (!mList.includes(selectedModel)) {
            setSelectedModel(mList[0]);
          }
        }
      })
      .catch(() => {});
  }, [apiKey]);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const filesArray = Array.from(e.target.files);
      const newAttachments = filesArray.map((file) => ({
        file,
        url: URL.createObjectURL(file),
      }));
      setAttachedFiles((prev) => [...prev, ...newAttachments]);
    }
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const removeAttachment = (index: number) => {
    setAttachedFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const handleCopy = (text: string, idx: number) => {
    navigator.clipboard.writeText(text);
    setCopiedIdx(idx);
    setTimeout(() => setCopiedIdx(null), 2000);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() && attachedFiles.length === 0) return;
    if (!apiKey) {
      alert('Сначала укажите API-ключ в настройках.');
      return;
    }

    let content: any = input;
    if (attachedFiles.length > 0) {
      content = [];
      if (input.trim()) content.push({ type: 'text', text: input });
      for (const att of attachedFiles) {
        const b64 = await fileToBase64(att.file);
        content.push({ type: 'image_url', image_url: { url: b64 } });
      }
    }

    const newUserMsg: Message = { role: 'user', content };
    const updatedMessages = [...messages, newUserMsg];
    setMessages(updatedMessages);
    setInput('');
    setAttachedFiles([]);
    setIsLoading(true);

    try {
      const response = await fetch(apiUrl('/v1/chat/completions'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${apiKey}`,
        },
        body: JSON.stringify({
          model: selectedModel,
          messages: updatedMessages,
        }),
      });

      if (!response.ok) {
        const errJson = await response.json().catch(() => ({}));
        throw new Error(errJson.detail || `HTTP ${response.status}`);
      }

      const data = await response.json();
      const assistantMsg: Message = data.choices[0].message;
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err: any) {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: `Ошибка запроса: ${err.message}` },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full bg-background relative overflow-hidden">
      {/* Chat Header */}
      <div className="h-14 px-6 border-b border-border/70 flex items-center justify-between bg-card/30 backdrop-blur-xs shrink-0 select-none">
        <div className="flex items-center gap-2">
          <MessageSquare className="w-4 h-4 text-primary" />
          <h1 className="font-semibold text-sm">Chat Playground</h1>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground bg-muted/50 border border-border/70 rounded-lg px-2.5 py-1">
            <Cpu className="w-3.5 h-3.5 text-primary" />
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              className="bg-transparent border-none outline-none font-mono text-xs text-foreground cursor-pointer"
            >
              {models.map((m) => (
                <option key={m} value={m} className="bg-popover text-foreground font-mono">
                  {m}
                </option>
              ))}
            </select>
          </div>

          {messages.length > 0 && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setMessages([])}
              className="h-7 px-2.5 text-xs gap-1.5 text-muted-foreground hover:text-destructive cursor-pointer"
              title="Очистить историю сообщений"
            >
              <Trash2 className="w-3.5 h-3.5" />
              <span>Очистить</span>
            </Button>
          )}
        </div>
      </div>

      {/* Messages List */}
      <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-5">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-muted-foreground select-none max-w-sm mx-auto text-center">
            <div className="w-12 h-12 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center text-primary mb-3 shadow-xs">
              <MessageSquare className="w-6 h-6" />
            </div>
            <h3 className="font-semibold text-foreground text-sm">Чат с моделью</h3>
            <p className="text-xs text-muted-foreground mt-1">
              Отправляйте текстовые промпты или прикрепляйте изображения для мультимодальных запросов.
            </p>
          </div>
        )}

        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex gap-3 max-w-3xl ${msg.role === 'user' ? 'ml-auto justify-end' : 'mr-auto justify-start'}`}
          >
            {msg.role === 'assistant' && (
              <div className="w-7 h-7 rounded-full bg-primary/15 text-primary border border-primary/25 flex items-center justify-center shrink-0 mt-1 shadow-xs">
                <Bot className="w-4 h-4" />
              </div>
            )}

            <div
              className={`rounded-2xl px-4 py-3 text-sm shadow-xs relative group ${
                msg.role === 'user'
                  ? 'bg-primary text-primary-foreground max-w-[85%]'
                  : 'bg-card border border-border/80 text-foreground max-w-[90%]'
              }`}
            >
              {typeof msg.content === 'string' ? (
                <div className="prose dark:prose-invert max-w-none text-sm break-words whitespace-pre-wrap">
                  <ReactMarkdown>{msg.content}</ReactMarkdown>
                </div>
              ) : (
                <div className="space-y-2">
                  {msg.content.map((part: any, j: number) => {
                    if (part.type === 'text') {
                      return (
                        <div key={j} className="prose dark:prose-invert max-w-none text-sm break-words whitespace-pre-wrap">
                          <ReactMarkdown>{part.text}</ReactMarkdown>
                        </div>
                      );
                    } else if (part.type === 'image_url') {
                      return (
                        <img
                          key={j}
                          src={part.image_url.url}
                          alt="Вложение"
                          className="max-w-[240px] rounded-lg border border-border/80"
                        />
                      );
                    }
                    return null;
                  })}
                </div>
              )}

              {msg.role === 'assistant' && typeof msg.content === 'string' && (
                <button
                  type="button"
                  onClick={() => handleCopy(msg.content, i)}
                  className="absolute top-2 right-2 p-1 rounded-md text-muted-foreground/60 hover:text-foreground hover:bg-muted opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer"
                  title="Копировать ответ"
                >
                  {copiedIdx === i ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                </button>
              )}
            </div>

            {msg.role === 'user' && (
              <div className="w-7 h-7 rounded-full bg-muted border border-border/80 flex items-center justify-center shrink-0 mt-1 text-muted-foreground shadow-xs">
                <User className="w-4 h-4" />
              </div>
            )}
          </div>
        ))}

        {isLoading && (
          <div className="flex gap-3 max-w-3xl mr-auto justify-start">
            <div className="w-7 h-7 rounded-full bg-primary/15 text-primary border border-primary/25 flex items-center justify-center shrink-0 mt-1">
              <Bot className="w-4 h-4" />
            </div>
            <div className="bg-card border border-border/80 text-foreground rounded-2xl px-4 py-3 flex gap-1.5 items-center">
              <div className="w-1.5 h-1.5 rounded-full bg-primary animate-bounce" />
              <div className="w-1.5 h-1.5 rounded-full bg-primary animate-bounce" style={{ animationDelay: '0.15s' }} />
              <div className="w-1.5 h-1.5 rounded-full bg-primary animate-bounce" style={{ animationDelay: '0.3s' }} />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input Bar */}
      <div className="p-4 bg-card/40 border-t border-border/70 backdrop-blur-xs">
        <form onSubmit={handleSubmit} className="max-w-4xl mx-auto space-y-2">
          {attachedFiles.length > 0 && (
            <div className="flex gap-2 overflow-x-auto pb-1">
              {attachedFiles.map((att, i) => (
                <div key={i} className="relative group shrink-0">
                  <img src={att.url} alt="attached" className="w-14 h-14 object-cover rounded-lg border border-border/80 shadow-xs" />
                  <button
                    type="button"
                    onClick={() => removeAttachment(i)}
                    className="absolute -top-1.5 -right-1.5 bg-destructive text-destructive-foreground rounded-full p-0.5 shadow-sm hover:scale-110 transition-transform cursor-pointer"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </div>
              ))}
            </div>
          )}

          <div className="relative flex items-center">
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="absolute left-3 p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/70 transition-colors cursor-pointer"
              title="Прикрепить изображение"
            >
              <ImageIcon className="w-4 h-4" />
            </button>
            <input
              type="file"
              ref={fileInputRef}
              className="hidden"
              multiple
              accept="image/*"
              onChange={handleFileSelect}
            />
            <Input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={`Сообщение для ${selectedModel}...`}
              className="pl-11 pr-12 h-11 rounded-xl bg-card border-border/80 shadow-xs text-sm"
              disabled={isLoading}
            />
            <Button
              type="submit"
              size="sm"
              disabled={isLoading || (!input.trim() && attachedFiles.length === 0)}
              className="absolute right-2 h-7 w-7 p-0 rounded-lg cursor-pointer shrink-0"
              title="Отправить (Enter)"
            >
              <Send className="w-3.5 h-3.5" />
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
