'use client';

import { useEffect, useRef, useState } from 'react';
import { RefreshCcw, X } from 'lucide-react';
import { fetchChatHistory, sendChatMessage, streamChatMessage } from '@/lib/api';
import type { CommuneFeature } from '@/lib/api';

function getSessionId(): string {
  if (typeof window === 'undefined') return 'ssr';
  const key = 'teyva_session_id';
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

type Role = 'user' | 'assistant';
type ChatMessage = {
  id: string;
  role: Role;
  content: string;
  ts: number;
  status?: 'sending' | 'error' | 'ok';
};

type SelectedCommune = CommuneFeature['properties'] | null;

const SUGGESTIONS = (selected: SelectedCommune) => {
  const base = [
    '¿Qué comunas están en alerta?',
    'Pronóstico de lluvia',
    '¿Qué barrios vigilar?',
  ];
  if (selected) {
    base.unshift(`Riesgo en ${selected.nombre_comuna}`);
  }
  return base.slice(0, 3);
};

const HERO_BG = 'linear-gradient(140deg, oklch(0.32 0.06 42) 0%, oklch(0.38 0.08 38) 55%, oklch(0.34 0.07 30) 100%)';
const BRAND_BG = 'linear-gradient(140deg, oklch(0.58 0.14 42) 0%, oklch(0.45 0.10 38) 100%)';

interface TeyvaChatWidgetProps {
  selectedCommune: SelectedCommune;
  externalOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
}

export function TeyvaChatWidget({ selectedCommune, externalOpen, onOpenChange }: TeyvaChatWidgetProps) {
  const [internalOpen, setInternalOpen] = useState(false);
  const open = externalOpen ?? internalOpen;
  const setOpen = (val: boolean) => {
    setInternalOpen(val);
    onOpenChange?.(val);
  };
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const sessionId = useRef<string>('');
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    sessionId.current = getSessionId();
    (async () => {
      try {
        const history = await fetchChatHistory(sessionId.current);
        if (history.length > 0) {
          setMessages(
            history
              .filter((m) => m.role === 'user' || m.role === 'assistant')
              .map((m, idx) => ({
                id: m.id ?? `h_${idx}_${m.ts ?? Date.now()}`,
                role: m.role as Role,
                content: m.content,
                ts: m.ts ?? Date.now(),
                status: 'ok',
              }))
          );
        }
      } catch {
        // historia no disponible, empezamos limpio
      }
    })();
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, open]);

  async function sendMessage(text: string) {
    const trimmed = text.trim();
    if (!trimmed || sending) return;

    const userMsg: ChatMessage = { id: crypto.randomUUID(), role: 'user', content: trimmed, ts: Date.now(), status: 'ok' };
    const placeholder: ChatMessage = { id: crypto.randomUUID(), role: 'assistant', content: '', ts: Date.now(), status: 'sending' };

    setMessages((prev) => [...prev, userMsg, placeholder]);
    setInput('');
    setSending(true);

    const context = selectedCommune
      ? {
          selected_comuna_id: selectedCommune.commune_id,
          selected_comuna_name: selectedCommune.nombre_comuna,
          risk_level: selectedCommune.categoria_riesgo,
        }
      : null;

    try {
      const full = await streamChatMessage(
        trimmed,
        sessionId.current,
        (partial) => {
          setMessages((prev) =>
            prev.map((m) => (m.id === placeholder.id ? { ...m, content: partial, status: 'ok' } : m))
          );
        },
        context
      );
      // El stream terminó sin producir ningún texto (ej. endpoint devolvió
      // solo "[DONE]"): mostramos un mensaje de reserva en vez de un bubble vacío.
      if (!full) {
        setMessages((prev) =>
          prev.map((m) => (m.id === placeholder.id ? { ...m, content: '(sin respuesta)', status: 'ok' } : m))
        );
      }
    } catch {
      // Fallback: si el streaming falla (endpoint /stream no disponible, navegador
      // sin soporte de ReadableStream, etc.) reintentamos con el flujo clásico
      // no-streaming antes de mostrar un error al usuario.
      try {
        const reply = await sendChatMessage(trimmed, sessionId.current, context);
        setMessages((prev) =>
          prev.map((m) => (m.id === placeholder.id ? { ...m, content: reply || '(sin respuesta)', status: 'ok' } : m))
        );
      } catch {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === placeholder.id
              ? { ...m, content: 'No pude conectar con TEYVA. Verifica tu conexión o reintenta.', status: 'error' }
              : m
          )
        );
      }
    } finally {
      setSending(false);
    }
  }

  function retryLast() {
    const lastUser = [...messages].reverse().find((m) => m.role === 'user');
    if (lastUser) void sendMessage(lastUser.content);
  }

  return (
    <div style={{ position: 'fixed', bottom: '26px', right: '26px', zIndex: 60, display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '14px' }}>
      {/* Panel del chat */}
      {open && (
        <div
          className="animate-teyva-pop"
          style={{
            width: '374px',
            height: '520px',
            display: 'flex',
            flexDirection: 'column',
            borderRadius: '24px',
            overflow: 'hidden',
            background: 'oklch(0.99 0.008 75)',
            border: '1px solid oklch(0.89 0.018 70)',
            boxShadow: '0 24px 60px -20px oklch(0.4 0.06 45 / 0.4)',
          }}
        >
          {/* Header */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '11px',
              padding: '16px 18px',
              background: HERO_BG,
              color: 'oklch(0.98 0.01 80)',
            }}
          >
            <div
              style={{
                height: '38px',
                width: '38px',
                borderRadius: '12px',
                background: 'oklch(1 0 0 / 0.16)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '18px',
              }}
            >
              🌦️
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '16px', lineHeight: 1 }}>
                Teyva
              </div>
              <div style={{ fontSize: '11.5px', color: 'oklch(1 0 0 / 0.78)', marginTop: '3px', display: 'flex', alignItems: 'center', gap: '5px' }}>
                <span style={{ height: '6px', width: '6px', borderRadius: '99px', background: 'oklch(0.72 0.14 150)', flexShrink: 0 }} />
                {selectedCommune ? `Viendo: ${selectedCommune.nombre_comuna}` : 'Asistente de riesgo · en línea'}
              </div>
            </div>
            <button
              onClick={() => setOpen(false)}
              style={{
                height: '30px',
                width: '30px',
                border: 'none',
                cursor: 'pointer',
                borderRadius: '9px',
                background: 'oklch(1 0 0 / 0.14)',
                color: 'oklch(0.98 0.01 80)',
                fontSize: '16px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
              aria-label="Cerrar"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* Mensajes */}
          <div
            ref={scrollRef}
            style={{
              flex: 1,
              overflowY: 'auto',
              padding: '18px',
              display: 'flex',
              flexDirection: 'column',
              gap: '12px',
              background: 'oklch(0.97 0.012 75)',
            }}
          >
            {messages.length === 0 && (
              <div
                style={{
                  borderRadius: '16px',
                  padding: '14px',
                  background: 'oklch(1 0 0)',
                  border: '1px solid oklch(0.91 0.018 70)',
                  fontSize: '13.5px',
                  lineHeight: 1.5,
                  color: 'oklch(0.32 0.04 45)',
                }}
              >
                ¡Hola! Soy Teyva 🌦️ Vigilo el riesgo de deslizamientos en Medellín. Pregúntame por cualquier comuna y te cuento cómo está hoy.
              </div>
            )}

            {messages.map((m) => (
              <Bubble key={m.id} message={m} />
            ))}

            {messages.some((m) => m.status === 'error') && (
              <button
                onClick={retryLast}
                style={{
                  alignSelf: 'center',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  borderRadius: '99px',
                  border: '1px solid oklch(0.89 0.018 70)',
                  background: 'oklch(0.99 0.008 75)',
                  padding: '6px 13px',
                  fontSize: '12px',
                  color: 'oklch(0.52 0.035 55)',
                  cursor: 'pointer',
                }}
              >
                <RefreshCcw className="h-3 w-3" /> Reintentar
              </button>
            )}
          </div>

          {/* Sugerencias + Input */}
          <div style={{ borderTop: '1px solid oklch(0.91 0.018 70)', padding: '12px 14px', background: 'oklch(0.99 0.008 75)' }}>
            <div style={{ display: 'flex', gap: '8px', overflowX: 'auto', paddingBottom: '10px' }}>
              {SUGGESTIONS(selectedCommune).map((s) => (
                <button
                  key={s}
                  onClick={() => void sendMessage(s)}
                  disabled={sending}
                  style={{
                    whiteSpace: 'nowrap',
                    cursor: 'pointer',
                    borderRadius: '99px',
                    border: '1px solid oklch(0.88 0.025 65)',
                    background: 'oklch(0.96 0.018 75)',
                    color: 'oklch(0.4 0.05 50)',
                    padding: '7px 13px',
                    fontFamily: 'var(--font-sans)',
                    fontSize: '12.5px',
                    fontWeight: 600,
                    opacity: sending ? 0.5 : 1,
                  }}
                >
                  {s}
                </button>
              ))}
            </div>

            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '9px',
                borderRadius: '14px',
                border: '1px solid oklch(0.89 0.02 68)',
                background: 'oklch(0.98 0.01 75)',
                padding: '7px 7px 7px 15px',
              }}
            >
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') void sendMessage(input); }}
                placeholder="Pregúntame sobre una comuna…"
                style={{
                  flex: 1,
                  border: 'none',
                  outline: 'none',
                  background: 'transparent',
                  fontFamily: 'var(--font-sans)',
                  fontSize: '14px',
                  color: 'oklch(0.3 0.04 45)',
                }}
              />
              <button
                onClick={() => void sendMessage(input)}
                disabled={!input.trim() || sending}
                style={{
                  height: '36px',
                  width: '36px',
                  border: 'none',
                  cursor: input.trim() && !sending ? 'pointer' : 'default',
                  borderRadius: '11px',
                  background: BRAND_BG,
                  color: 'oklch(0.98 0.01 80)',
                  fontSize: '16px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  opacity: !input.trim() || sending ? 0.45 : 1,
                }}
                aria-label="Enviar"
              >
                ➤
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Botón flotante */}
      <button
        onClick={() => setOpen(!open)}
        style={{
          height: '60px',
          width: '60px',
          border: 'none',
          cursor: 'pointer',
          borderRadius: '20px',
          background: BRAND_BG,
          boxShadow: '0 14px 32px -10px oklch(0.55 0.13 40 / 0.6)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: '26px',
          transition: 'transform 0.15s ease',
        }}
        onMouseEnter={(e) => (e.currentTarget.style.transform = 'translateY(-2px) scale(1.04)')}
        onMouseLeave={(e) => (e.currentTarget.style.transform = 'none')}
        aria-label={open ? 'Cerrar Teyva' : 'Abrir Teyva'}
      >
        {open ? '✕' : '💬'}
      </button>
    </div>
  );
}

function Bubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === 'user';
  const rowStyle: React.CSSProperties = { display: 'flex', justifyContent: isUser ? 'flex-end' : 'flex-start' };
  const bubbleStyle: React.CSSProperties = isUser
    ? {
        maxWidth: '80%',
        borderRadius: '16px 16px 4px 16px',
        padding: '11px 14px',
        fontSize: '13.5px',
        lineHeight: 1.5,
        background: 'linear-gradient(140deg, oklch(0.58 0.14 42) 0%, oklch(0.45 0.10 38) 100%)',
        color: 'oklch(0.98 0.01 80)',
      }
    : {
        maxWidth: '82%',
        borderRadius: '16px 16px 16px 4px',
        padding: '11px 14px',
        fontSize: '13.5px',
        lineHeight: 1.5,
        background: 'oklch(1 0 0)',
        border: '1px solid oklch(0.91 0.018 70)',
        color: 'oklch(0.32 0.04 45)',
      };

  return (
    <div style={rowStyle}>
      <div style={bubbleStyle}>
        {message.status === 'sending' ? (
          <span style={{ display: 'inline-flex', gap: '4px' }}>
            <Dot delay="0s" />
            <Dot delay="0.15s" />
            <Dot delay="0.3s" />
          </span>
        ) : (
          message.content
        )}
      </div>
    </div>
  );
}

function Dot({ delay }: { delay: string }) {
  return (
    <span
      className="inline-block h-1.5 w-1.5 animate-bounce rounded-full bg-current opacity-60"
      style={{ animationDelay: delay }}
    />
  );
}
