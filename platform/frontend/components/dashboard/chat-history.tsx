'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ArrowLeft, Clock, MessageSquare, RefreshCcw, Search, Sparkles, X } from 'lucide-react';
import {
  fetchChatHistory,
  fetchChatSessions,
  type ChatHistoryMessage,
  type ChatSessionSummary,
} from '@/lib/api';

function formatRelative(iso: string | null): string {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '—';
  const diffMs = Date.now() - date.getTime();
  const mins = Math.floor(diffMs / 60_000);
  if (mins < 1) return 'Ahora mismo';
  if (mins < 60) return `Hace ${mins} min`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `Hace ${hours} h`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `Hace ${days} día${days > 1 ? 's' : ''}`;
  return date.toLocaleDateString('es-CO', { day: '2-digit', month: 'short', year: 'numeric' });
}

function formatTime(iso: string | null | undefined): string {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit' });
}

function currentSessionId(): string | null {
  if (typeof window === 'undefined') return null;
  return window.localStorage.getItem('teyva_session_id');
}

export function ChatHistory() {
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState<ChatSessionSummary | null>(null);
  const [messages, setMessages] = useState<ChatHistoryMessage[]>([]);
  const [messagesLoading, setMessagesLoading] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mySessionId = useMemo(() => currentSessionId(), []);

  const loadSessions = useCallback(async (q: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchChatSessions({ q, limit: 100 });
      setSessions(data.sessions);
      setTotal(data.total);
    } catch {
      setError('No se pudo cargar el historial. Verifica que el backend esté en línea.');
      setSessions([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadSessions('');
  }, [loadSessions]);

  // Búsqueda con debounce para no saturar el backend
  const onQueryChange = (value: string) => {
    setQuery(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => void loadSessions(value), 350);
  };

  const openSession = useCallback(async (session: ChatSessionSummary) => {
    setSelected(session);
    setMessagesLoading(true);
    setMessages([]);
    try {
      const history = await fetchChatHistory(session.session_id);
      setMessages(history.filter((m) => m.role === 'user' || m.role === 'assistant'));
    } catch {
      setMessages([]);
    } finally {
      setMessagesLoading(false);
    }
  }, []);

  const listPanel = (
    <div
      className="teyva-card flex min-h-0 flex-col"
      style={{ overflow: 'hidden', flex: 1 }}
    >
      {/* Encabezado + búsqueda */}
      <div style={{ padding: '18px 18px 14px', borderBottom: '1px solid var(--border)' }}>
        <div className="flex items-center justify-between gap-2">
          <div>
            <h2 style={{ fontSize: '17px', fontWeight: 700, letterSpacing: '-0.01em' }}>
              Conversaciones
            </h2>
            <p style={{ fontSize: '12px', color: 'var(--muted-foreground)', marginTop: '2px' }}>
              {loading ? 'Cargando…' : `${total} sesión${total === 1 ? '' : 'es'} guardada${total === 1 ? '' : 's'}`}
            </p>
          </div>
          <button
            onClick={() => void loadSessions(query)}
            aria-label="Recargar historial"
            className="hover-lift press-scale"
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              height: '34px',
              width: '34px',
              borderRadius: '10px',
              border: '1px solid var(--border)',
              background: 'var(--card)',
              color: 'var(--muted-foreground)',
              cursor: 'pointer',
            }}
          >
            <RefreshCcw size={15} />
          </button>
        </div>

        <div style={{ position: 'relative', marginTop: '12px' }}>
          <Search
            size={15}
            style={{
              position: 'absolute',
              left: '12px',
              top: '50%',
              transform: 'translateY(-50%)',
              color: 'var(--muted-foreground)',
              pointerEvents: 'none',
            }}
          />
          <input
            value={query}
            onChange={(e) => onQueryChange(e.target.value)}
            placeholder="Buscar por comuna, tema o palabra clave…"
            style={{
              width: '100%',
              padding: '9px 34px 9px 34px',
              borderRadius: '11px',
              border: '1px solid var(--input)',
              background: 'var(--background)',
              fontSize: '13.5px',
              fontFamily: 'var(--font-sans)',
              color: 'var(--foreground)',
              outline: 'none',
            }}
          />
          {query && (
            <button
              onClick={() => onQueryChange('')}
              aria-label="Limpiar búsqueda"
              style={{
                position: 'absolute',
                right: '8px',
                top: '50%',
                transform: 'translateY(-50%)',
                display: 'flex',
                border: 'none',
                background: 'transparent',
                color: 'var(--muted-foreground)',
                cursor: 'pointer',
                padding: '4px',
              }}
            >
              <X size={14} />
            </button>
          )}
        </div>
      </div>

      {/* Lista */}
      <div className="teyva-scroll" style={{ flex: 1, overflowY: 'auto', padding: '10px' }}>
        {loading && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', padding: '4px' }}>
            {[0, 1, 2, 3, 4].map((i) => (
              <div key={i} className="skeleton-shimmer" style={{ height: '74px' }} />
            ))}
          </div>
        )}

        {!loading && error && (
          <div style={{ padding: '28px 18px', textAlign: 'center', color: 'var(--muted-foreground)', fontSize: '13.5px' }}>
            {error}
          </div>
        )}

        {!loading && !error && sessions.length === 0 && (
          <div style={{ padding: '36px 20px', textAlign: 'center' }}>
            <MessageSquare size={28} style={{ color: 'var(--muted-foreground)', margin: '0 auto 10px' }} />
            <p style={{ fontSize: '14px', fontWeight: 600 }}>
              {query ? 'Sin resultados para tu búsqueda' : 'Aún no hay conversaciones'}
            </p>
            <p style={{ fontSize: '12.5px', color: 'var(--muted-foreground)', marginTop: '6px' }}>
              {query
                ? 'Prueba con otra palabra clave o el nombre de una comuna.'
                : 'Habla con Teyva desde el dashboard y tus conversaciones aparecerán aquí.'}
            </p>
          </div>
        )}

        {!loading && !error && sessions.length > 0 && (
          <div className="anim-stagger" style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {sessions.map((s) => {
              const active = selected?.session_id === s.session_id;
              const isMine = s.session_id === mySessionId;
              return (
                <button
                  key={s.session_id}
                  onClick={() => void openSession(s)}
                  style={{
                    textAlign: 'left',
                    width: '100%',
                    border: '1px solid',
                    borderColor: active ? 'var(--primary)' : 'transparent',
                    borderRadius: '14px',
                    background: active ? 'var(--secondary)' : 'transparent',
                    padding: '12px 14px',
                    cursor: 'pointer',
                    fontFamily: 'var(--font-sans)',
                    transition: 'background 0.15s ease, border-color 0.15s ease',
                  }}
                  onMouseEnter={(e) => {
                    if (!active) e.currentTarget.style.background = 'var(--muted)';
                  }}
                  onMouseLeave={(e) => {
                    if (!active) e.currentTarget.style.background = 'transparent';
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span
                      style={{
                        flex: 1,
                        minWidth: 0,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        fontSize: '13.5px',
                        fontWeight: 650,
                        color: 'var(--foreground)',
                      }}
                    >
                      {s.title}
                    </span>
                    {isMine && (
                      <span
                        style={{
                          flexShrink: 0,
                          fontSize: '10px',
                          fontWeight: 700,
                          textTransform: 'uppercase',
                          letterSpacing: '0.08em',
                          color: 'var(--primary-foreground)',
                          background: 'var(--primary)',
                          borderRadius: '99px',
                          padding: '2px 8px',
                        }}
                      >
                        Actual
                      </span>
                    )}
                  </div>
                  <p
                    style={{
                      marginTop: '4px',
                      fontSize: '12.5px',
                      color: 'var(--muted-foreground)',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {s.preview_role === 'assistant' ? 'Teyva: ' : ''}
                    {s.preview || 'Sin mensajes'}
                  </p>
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '12px',
                      marginTop: '6px',
                      fontSize: '11.5px',
                      color: 'var(--muted-foreground)',
                    }}
                  >
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                      <Clock size={11} /> {formatRelative(s.last_message_at)}
                    </span>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                      <MessageSquare size={11} /> {s.message_count} mensajes
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );

  const viewerPanel = (
    <div className="teyva-card flex min-h-0 flex-col" style={{ overflow: 'hidden', flex: 1 }}>
      {!selected ? (
        <div
          style={{
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '12px',
            padding: '40px 24px',
            textAlign: 'center',
          }}
        >
          <div
            style={{
              height: '52px',
              width: '52px',
              borderRadius: '16px',
              background: 'var(--gradient-brand)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: 'var(--shadow-soft)',
            }}
          >
            <Sparkles size={24} color="white" />
          </div>
          <p style={{ fontSize: '15px', fontWeight: 650 }}>Selecciona una conversación</p>
          <p style={{ fontSize: '13px', color: 'var(--muted-foreground)', maxWidth: '320px' }}>
            Aquí verás el detalle completo de la conversación: preguntas, respuestas de Teyva y las
            fuentes consultadas.
          </p>
        </div>
      ) : (
        <>
          <div
            style={{
              padding: '16px 18px',
              borderBottom: '1px solid var(--border)',
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
            }}
          >
            <button
              onClick={() => setSelected(null)}
              aria-label="Volver a la lista"
              className="press-scale md:hidden"
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                height: '32px',
                width: '32px',
                borderRadius: '10px',
                border: '1px solid var(--border)',
                background: 'var(--card)',
                color: 'var(--muted-foreground)',
                cursor: 'pointer',
                flexShrink: 0,
              }}
            >
              <ArrowLeft size={15} />
            </button>
            <div style={{ minWidth: 0, flex: 1 }}>
              <h3
                style={{
                  fontSize: '15px',
                  fontWeight: 700,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {selected.title}
              </h3>
              <p style={{ fontSize: '12px', color: 'var(--muted-foreground)', marginTop: '2px' }}>
                Inició {formatRelative(selected.started_at)} · {selected.message_count} mensajes
              </p>
            </div>
          </div>

          <div
            className="teyva-scroll"
            style={{
              flex: 1,
              overflowY: 'auto',
              padding: '18px',
              display: 'flex',
              flexDirection: 'column',
              gap: '12px',
              background: 'var(--background)',
            }}
          >
            {messagesLoading &&
              [0, 1, 2].map((i) => (
                <div
                  key={i}
                  className="skeleton-shimmer"
                  style={{
                    height: '58px',
                    width: '70%',
                    alignSelf: i % 2 === 0 ? 'flex-end' : 'flex-start',
                    borderRadius: '16px',
                  }}
                />
              ))}

            {!messagesLoading && messages.length === 0 && (
              <p style={{ textAlign: 'center', fontSize: '13px', color: 'var(--muted-foreground)', padding: '30px 0' }}>
                No se pudieron cargar los mensajes de esta conversación.
              </p>
            )}

            {!messagesLoading &&
              messages.map((m, idx) => {
                const isUser = m.role === 'user';
                return (
                  <div
                    key={m.id ?? `${selected.session_id}_${idx}`}
                    className="anim-fade-in"
                    style={{
                      alignSelf: isUser ? 'flex-end' : 'flex-start',
                      maxWidth: 'min(85%, 560px)',
                    }}
                  >
                    <div
                      style={{
                        borderRadius: isUser ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
                        background: isUser ? 'var(--gradient-brand)' : 'var(--card)',
                        border: isUser ? 'none' : '1px solid var(--border)',
                        color: isUser ? 'var(--primary-foreground)' : 'var(--foreground)',
                        padding: '11px 14px',
                        fontSize: '13.5px',
                        lineHeight: 1.55,
                        whiteSpace: 'pre-wrap',
                        wordBreak: 'break-word',
                        boxShadow: 'var(--shadow-soft)',
                      }}
                    >
                      {m.content}
                    </div>
                    <div
                      style={{
                        marginTop: '4px',
                        fontSize: '10.5px',
                        color: 'var(--muted-foreground)',
                        textAlign: isUser ? 'right' : 'left',
                        padding: '0 4px',
                      }}
                    >
                      {isUser ? 'Tú' : 'Teyva'}
                      {formatTime(m.created_at) ? ` · ${formatTime(m.created_at)}` : ''}
                    </div>
                  </div>
                );
              })}
          </div>
        </>
      )}
    </div>
  );

  return (
    <section
      aria-label="Historial de conversaciones"
      className="anim-fade-up"
      style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}
    >
      <div>
        <h2 className="teyva-page-title">Historial de conversaciones</h2>
        <p className="teyva-page-subtitle" style={{ maxWidth: '560px' }}>
          Todas las conversaciones con Teyva quedan guardadas. Busca por comuna o tema y retoma
          cualquier consulta anterior.
        </p>
      </div>

      {/* Desktop: dos paneles lado a lado. Mobile: lista o visor según selección */}
      <div
        className="grid gap-4 md:grid-cols-[minmax(300px,380px)_1fr]"
        style={{ height: 'min(680px, calc(100vh - 240px))', minHeight: '480px' }}
      >
        <div className={selected ? 'hidden min-h-0 md:flex md:flex-col' : 'flex min-h-0 flex-col'}>
          {listPanel}
        </div>
        <div className={selected ? 'flex min-h-0 flex-col' : 'hidden min-h-0 md:flex md:flex-col'}>
          {viewerPanel}
        </div>
      </div>
    </section>
  );
}
