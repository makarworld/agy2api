import React, { useState, useRef, useEffect } from 'react';
import { useApiKey } from '../hooks/use-api-key';
import { fileToBase64 } from '../lib/utils';
import { apiUrl } from '../lib/api';

import { Input } from '../components/ui/input';
import { Send, Image as ImageIcon, X } from 'lucide-react';
import ReactMarkdown from 'react-markdown';

type Message = {
  role: 'user' | 'assistant';
  content: any; // Can be string or array of parts for multimodal
};

export function ChatPage() {
  const { apiKey } = useApiKey();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [attachedFiles, setAttachedFiles] = useState<{file: File, url: string}[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const filesArray = Array.from(e.target.files);
      const newAttachments = filesArray.map(file => ({
        file,
        url: URL.createObjectURL(file)
      }));
      setAttachedFiles(prev => [...prev, ...newAttachments]);
    }
    // reset input
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const removeAttachment = (index: number) => {
    setAttachedFiles(prev => prev.filter((_, i) => i !== index));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() && attachedFiles.length === 0) return;
    if (!apiKey) {
      alert("Please set your API key in the Keys page first.");
      return;
    }

    // Build message content
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
          'Authorization': `Bearer ${apiKey}`
        },
        body: JSON.stringify({
          model: 'Gemini 3.6 Flash (High)',
          messages: updatedMessages
        })
      });

      if (!response.ok) {
        throw new Error(`API Error: ${response.status}`);
      }

      const data = await response.json();
      const assistantMsg: Message = data.choices[0].message;
      setMessages(prev => [...prev, assistantMsg]);

    } catch (err: any) {
      setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${err.message}` }]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full bg-background relative">
      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
            <MessageSquare className="w-12 h-12 mb-4 opacity-50" />
            <p>Start chatting with AGY...</p>
          </div>
        )}
        
        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[80%] rounded-xl px-4 py-3 ${
              msg.role === 'user' ? 'bg-primary text-primary-foreground' : 'bg-muted text-foreground'
            }`}>
              {typeof msg.content === 'string' ? (
                <div className="md-render prose dark:prose-invert max-w-none">
                  <ReactMarkdown>{msg.content}</ReactMarkdown>
                </div>
              ) : (
                <div className="space-y-2">
                  {msg.content.map((part: any, j: number) => {
                    if (part.type === 'text') {
                      return <div key={j} className="md-render prose dark:prose-invert max-w-none"><ReactMarkdown>{part.text}</ReactMarkdown></div>;
                    } else if (part.type === 'image_url') {
                      return <img key={j} src={part.image_url.url} alt="attachment" className="max-w-[200px] rounded-md border" />;
                    }
                    return null;
                  })}
                </div>
              )}
            </div>
          </div>
        ))}
        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-muted text-foreground max-w-[80%] rounded-xl px-4 py-3 flex gap-1 items-center">
              <div className="w-2 h-2 rounded-full bg-current animate-bounce" />
              <div className="w-2 h-2 rounded-full bg-current animate-bounce" style={{ animationDelay: '0.2s' }} />
              <div className="w-2 h-2 rounded-full bg-current animate-bounce" style={{ animationDelay: '0.4s' }} />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="p-4 bg-background border-t">
        <form onSubmit={handleSubmit} className="max-w-4xl mx-auto">
          {attachedFiles.length > 0 && (
            <div className="flex gap-2 mb-2 overflow-x-auto pb-2">
              {attachedFiles.map((att, i) => (
                <div key={i} className="relative group shrink-0">
                  <img src={att.url} alt="attached" className="w-16 h-16 object-cover rounded-md border" />
                  <button
                    type="button"
                    onClick={() => removeAttachment(i)}
                    className="absolute -top-2 -right-2 bg-destructive text-destructive-foreground rounded-full p-0.5 opacity-0 group-hover:opacity-100 transition-opacity"
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
              className="absolute left-3 text-muted-foreground hover:text-foreground transition-colors"
            >
              <ImageIcon className="w-5 h-5" />
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
              placeholder="Message AGY..."
              className="pl-10 pr-12 py-6 rounded-2xl bg-card border-border shadow-sm text-base focus-visible:ring-1"
            />
            <button
              type="submit"
              disabled={isLoading || (!input.trim() && attachedFiles.length === 0)}
              className="absolute right-3 p-1.5 bg-primary text-primary-foreground rounded-xl disabled:opacity-50 transition-colors"
            >
              <Send className="w-4 h-4" />
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function MessageSquare(props: any) {
  return (
    <svg
      {...props}
      xmlns="http://www.w3.org/2000/svg"
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  );
}
