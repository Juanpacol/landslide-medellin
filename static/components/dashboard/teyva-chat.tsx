'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { MessageCircle, Send, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { sendChatMessage } from '@/lib/api';

function getOrCreateSessionId(): string {
  if (typeof window === 'undefined') return 'ssr';
  const key = 'teyva_chat_session_id';
  let id = window.localStorage.getItem(key);
  if (!id) {
    id =
      typeof crypto !== 'undefined' && crypto.randomUUID
        ? crypto.randomUUID()
        : `sess_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
    window.localStorage.setItem(key, id);
  }
  return id;
}

type Msg = { role: 'user' | 'assistant'; content: string };

export function TeyvaChatWidget() {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Msg[]>([]);
  const [pending, setPending] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, open]);

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || pending) return;
    setInput('');
    setMessages((m) => [...m, { role: 'user', content: text }]);
    setPending(true);
    try {
      const sessionId = getOrCreateSessionId();
      const reply = await sendChatMessage(text, sessionId);
      setMessages((m) => [...m, { role: 'assistant', content: reply }]);
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Error al enviar el mensaje';
      setMessages((m) => [...m, { role: 'assistant', content: `No se pudo contactar la API: ${msg}` }]);
    } finally {
      setPending(false);
    }
  }, [input, pending]);

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col items-end gap-2">
      {open && (
        <div className="w-[min(100vw-2rem,380px)] h-[min(70vh,480px)] flex flex-col rounded-lg border border-[#334155] bg-[#1e293b] shadow-xl overflow-hidden">
          <div className="flex items-center justify-between px-3 py-2 border-b border-[#334155] bg-[#0f172a]/80">
            <span className="text-sm font-medium text-[#f1f5f9]">Asistente TEYVA</span>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-[#94a3b8]"
              onClick={() => setOpen(false)}
              aria-label="Cerrar chat"
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
          <div className="flex-1 overflow-y-auto px-3 py-2 space-y-3">
            {messages.length === 0 && (
              <p className="text-xs text-[#94a3b8] leading-relaxed">
                Pregunte por riesgo de deslizamientos, comunas o alertas. Requiere API en{' '}
                <code className="text-[#38bdf8]">NEXT_PUBLIC_TEYVA_API_URL</code>.
              </p>
            )}
            {messages.map((m, i) => (
              <div
                key={i}
                className={`text-sm rounded-md px-2 py-1.5 max-w-[95%] ${
                  m.role === 'user'
                    ? 'ml-auto bg-[#3b82f6]/25 text-[#e2e8f0]'
                    : 'mr-auto bg-[#334155]/60 text-[#e2e8f0]'
                }`}
              >
                {m.content}
              </div>
            ))}
            <div ref={bottomRef} />
          </div>
          <div className="p-2 border-t border-[#334155] flex gap-2 bg-[#0f172a]/50">
            <Textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Escriba su mensaje…"
              className="min-h-[44px] max-h-28 resize-none bg-[#0f172a] border-[#475569] text-[#f1f5f9] text-sm"
              disabled={pending}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  void send();
                }
              }}
            />
            <Button
              type="button"
              className="shrink-0 self-end"
              onClick={() => void send()}
              disabled={pending || !input.trim()}
            >
              <Send className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
      <Button
        type="button"
        size="lg"
        className="rounded-full h-14 w-14 shadow-lg"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label={open ? 'Cerrar asistente' : 'Abrir asistente'}
      >
        <MessageCircle className="h-6 w-6" />
      </Button>
    </div>
  );
}
