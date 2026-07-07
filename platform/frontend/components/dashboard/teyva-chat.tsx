'use client';

import { useEffect, useRef, useState } from 'react';
import { RefreshCcw, X } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
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

// Nexura blue paleta (updated from terracota)
const HERO_BG = 'linear-gradient(140deg, oklch(0.32 0.08 258.9) 0%, oklch(0.38 0.10 258.9) 55%, oklch(0.34 0.09 258.9) 100%)';
const BRAND_BG = 'linear-gradient(140deg, oklch(0.625 0.191 258.9) 0%, oklch(0.68 0.17 258.9) 100%)';

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
            background: 'oklch(0.99 0.006 256.3)',
            border: '1px solid oklch(0.89 0.012 256.3)',
            boxShadow: '0 24px 60px -20px oklch(0.4 0.1 258.9 / 0.4)',
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
              background: 'oklch(0.96 0.014 256.3)',
            }}
          >
            {messages.length === 0 && (
              <div
                style={{
                  borderRadius: '16px',
                  padding: '14px',
                  background: 'oklch(1 0 0)',
                  border: '1px solid oklch(0.89 0.012 256.3)',
                  fontSize: '13.5px',
                  lineHeight: 1.5,
                  color: 'oklch(0.26 0.014 264)',
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
                  border: '1px solid oklch(0.89 0.012 256.3)',
                  background: 'oklch(0.99 0.006 256.3)',
                  padding: '6px 13px',
                  fontSize: '12px',
                  color: 'oklch(0.52 0.018 264)',
                  cursor: 'pointer',
                }}
              >
                <RefreshCcw className="h-3 w-3" /> Reintentar
              </button>
            )}
          </div>

          {/* Sugerencias + Input */}
          <div style={{ borderTop: '1px solid oklch(0.89 0.012 256.3)', padding: '12px 14px', background: 'oklch(0.99 0.006 256.3)' }}>
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
                    border: '1px solid oklch(0.88 0.02 258.9)',
                    background: 'oklch(0.93 0.014 256.3)',
                    color: 'oklch(0.4 0.06 258.9)',
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
                border: '1px solid oklch(0.89 0.014 256.3)',
                background: 'oklch(0.98 0.01 256.3)',
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
                  color: 'oklch(0.26 0.014 264)',
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
          boxShadow: '0 14px 32px -10px oklch(0.55 0.19 258.9 / 0.6)',
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

// Componentes markdown para el estilo compacto de las burbujas de chat: sin
// márgenes por defecto de <p>/<ul>, viñetas visibles a tamaño reducido.
const MARKDOWN_COMPONENTS = {
  p: ({ children }: { children?: React.ReactNode }) => (
    <p style={{ margin: '0 0 8px 0' }}>{children}</p>
  ),
  ul: ({ children }: { children?: React.ReactNode }) => (
    <ul style={{ margin: '0 0 8px 0', paddingLeft: '18px' }}>{children}</ul>
  ),
  ol: ({ children }: { children?: React.ReactNode }) => (
    <ol style={{ margin: '0 0 8px 0', paddingLeft: '18px' }}>{children}</ol>
  ),
  li: ({ children }: { children?: React.ReactNode }) => (
    <li style={{ marginBottom: '3px' }}>{children}</li>
  ),
  strong: ({ children }: { children?: React.ReactNode }) => (
    <strong style={{ fontWeight: 700 }}>{children}</strong>
  ),
  h1: ({ children }: { children?: React.ReactNode }) => (
    <div style={{ fontWeight: 700, fontSize: '14px', margin: '0 0 6px 0' }}>{children}</div>
  ),
  h2: ({ children }: { children?: React.ReactNode }) => (
    <div style={{ fontWeight: 700, fontSize: '13.5px', margin: '0 0 6px 0' }}>{children}</div>
  ),
  h3: ({ children }: { children?: React.ReactNode }) => (
    <div style={{ fontWeight: 600, fontSize: '13px', margin: '0 0 6px 0' }}>{children}</div>
  ),
  code: ({ children }: { children?: React.ReactNode }) => (
    <code
      style={{
        background: 'oklch(0.92 0.014 256.3)',
        borderRadius: '4px',
        padding: '1px 5px',
        fontSize: '12px',
        fontFamily: 'ui-monospace, monospace',
      }}
    >
      {children}
    </code>
  ),
};

function Bubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === 'user';
  const rowStyle: React.CSSProperties = { display: 'flex', justifyContent: isUser ? 'flex-end' : 'flex-start' };

  const bubbleStyle: React.CSSProperties = isUser
    ? {
        maxWidth: '80%',
        borderRadius: '14px 4px 14px 14px',
        padding: '10px 13px',
        fontSize: '13px',
        lineHeight: 1.6,
        background: 'oklch(0.625 0.191 258.9)',
        color: 'oklch(0.98 0.01 80)',
        wordWrap: 'break-word',
        whiteSpace: 'pre-wrap',
      }
    : {
        maxWidth: '82%',
        borderRadius: '4px 14px 14px 14px',
        padding: '11px 13px',
        fontSize: '13px',
        lineHeight: 1.6,
        background: 'oklch(0.98 0.006 256.3)',
        border: '1px solid oklch(0.89 0.012 256.3)',
        color: 'oklch(0.26 0.014 264)',
        wordWrap: 'break-word',
      };

  return (
    <div style={rowStyle}>
      <div style={bubbleStyle}>
        {message.status === 'sending' ? (
          <span style={{ display: 'inline-flex', gap: '4px', alignItems: 'center' }}>
            <Dot delay="0s" />
            <Dot delay="0.15s" />
            <Dot delay="0.3s" />
          </span>
        ) : message.status === 'error' ? (
          <span style={{ color: 'inherit', fontWeight: 500 }}>⚠️ {message.content}</span>
        ) : isUser ? (
          message.content
        ) : (
          <ReactMarkdown components={MARKDOWN_COMPONENTS}>{message.content}</ReactMarkdown>
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
