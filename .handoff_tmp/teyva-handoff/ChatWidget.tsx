import { useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  Bot,
  MessageCircle,
  RefreshCcw,
  Send,
  Sparkles,
  X,
} from "lucide-react";
import type { Comuna } from "@/lib/teyva-data";

type Role = "user" | "assistant";
interface ChatMessage {
  id: string;
  role: Role;
  content: string;
  ts: number;
  status?: "sending" | "error" | "ok";
}

const SUGGESTIONS = (selected: Comuna | null) => {
  const base = [
    "¿Qué comunas están en riesgo crítico hoy?",
    "Resume las alertas activas",
    "Compara la comuna 1 vs comuna 8",
  ];
  if (selected) {
    base.unshift(`¿Por qué subió el riesgo en ${selected.name}?`);
  }
  return base;
};

function getSessionId(): string {
  if (typeof window === "undefined") return "ssr";
  let id = window.localStorage.getItem("teyva_session_id");
  if (!id) {
    id =
      "sess_" +
      Math.random().toString(36).slice(2) +
      Date.now().toString(36);
    window.localStorage.setItem("teyva_session_id", id);
  }
  return id;
}

const API_BASE = "/api"; // FastAPI montado bajo /api

export function ChatWidget({ selected }: { selected: Comuna | null }) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [historyError, setHistoryError] = useState(false);
  const sessionId = useRef<string>("");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    sessionId.current = getSessionId();
    // Cargar historial previo (best-effort)
    (async () => {
      try {
        const r = await fetch(
          `${API_BASE}/chat/history/${sessionId.current}`,
          { method: "GET" },
        );
        if (!r.ok) throw new Error("history");
        const data = (await r.json()) as { messages?: ChatMessage[] };
        if (Array.isArray(data.messages) && data.messages.length) {
          setMessages(data.messages.map((m) => ({ ...m, status: "ok" })));
        }
      } catch {
        setHistoryError(true);
      }
    })();
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, open]);

  async function sendMessage(text: string) {
    const trimmed = text.trim();
    if (!trimmed || sending) return;
    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: trimmed,
      ts: Date.now(),
      status: "ok",
    };
    const placeholder: ChatMessage = {
      id: crypto.randomUUID(),
      role: "assistant",
      content: "",
      ts: Date.now(),
      status: "sending",
    };
    setMessages((prev) => [...prev, userMsg, placeholder]);
    setInput("");
    setSending(true);

    try {
      const r = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId.current,
          message: trimmed,
          context: selected
            ? {
                selected_comuna_id: selected.id,
                selected_comuna_name: selected.name,
                risk_level: selected.riskLevel,
              }
            : null,
        }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = (await r.json()) as { reply?: string; answer?: string };
      const reply = data.reply ?? data.answer ?? "(sin respuesta)";
      setMessages((prev) =>
        prev.map((m) =>
          m.id === placeholder.id
            ? { ...m, content: reply, status: "ok" }
            : m,
        ),
      );
    } catch {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === placeholder.id
            ? {
                ...m,
                content:
                  "No pude conectar con TEYVA. Verifica tu conexión o reintenta.",
                status: "error",
              }
            : m,
        ),
      );
    } finally {
      setSending(false);
    }
  }

  function retryLast() {
    const lastUser = [...messages].reverse().find((m) => m.role === "user");
    if (lastUser) sendMessage(lastUser.content);
  }

  return (
    <>
      {/* Botón flotante */}
      {!open && (
        <button
          onClick={() => setOpen(true)}
          className="fixed bottom-6 right-6 z-50 flex h-14 w-14 items-center justify-center rounded-full bg-[image:var(--gradient-leaf)] text-white shadow-[var(--shadow-elevated)] transition-transform hover:scale-105"
          aria-label="Abrir Asistente TEYVA"
        >
          <MessageCircle className="h-6 w-6" />
          <span className="absolute -top-1 -right-1 h-3 w-3 rounded-full bg-[var(--sun)] ring-2 ring-background" />
        </button>
      )}

      {/* Panel */}
      {open && (
        <div className="fixed bottom-6 right-6 z-50 flex h-[640px] max-h-[calc(100vh-3rem)] w-[420px] max-w-[calc(100vw-2rem)] flex-col overflow-hidden rounded-3xl border border-border/60 bg-card shadow-[var(--shadow-elevated)]">
          {/* Header */}
          <div className="flex items-center justify-between gap-2 border-b border-border/60 bg-[image:var(--gradient-hero)] p-4 text-white">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-white/15 backdrop-blur">
                <Sparkles className="h-4 w-4" />
              </div>
              <div>
                <div className="font-display text-sm font-700 leading-none">
                  Asistente TEYVA
                </div>
                <div className="mt-1 text-[11px] opacity-80">
                  {selected ? `Contexto: ${selected.name}` : "Sin comuna seleccionada"}
                </div>
              </div>
            </div>
            <button
              onClick={() => setOpen(false)}
              className="flex h-8 w-8 items-center justify-center rounded-lg text-white/80 transition hover:bg-white/15 hover:text-white"
              aria-label="Cerrar"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* Mensajes */}
          <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto p-4">
            {messages.length === 0 && (
              <div className="rounded-2xl bg-muted/60 p-4 text-sm text-muted-foreground">
                Hola 👋, soy <strong className="text-foreground">TEYVA</strong>.
                Pregúntame por el riesgo de deslizamientos en cualquier comuna de
                Medellín, alertas activas o explicaciones del modelo.
                {historyError && (
                  <div className="mt-2 flex items-center gap-1.5 text-[11px] text-muted-foreground/80">
                    <AlertCircle className="h-3 w-3" />
                    No se pudo cargar historial previo.
                  </div>
                )}
              </div>
            )}

            {messages.map((m) => (
              <Bubble key={m.id} message={m} />
            ))}

            {messages.some((m) => m.status === "error") && (
              <button
                onClick={retryLast}
                className="mx-auto flex items-center gap-1.5 rounded-full border border-border bg-card px-3 py-1 text-xs text-muted-foreground hover:bg-muted"
              >
                <RefreshCcw className="h-3 w-3" /> Reintentar
              </button>
            )}
          </div>

          {/* Sugerencias */}
          <div className="flex flex-wrap gap-1.5 border-t border-border/60 bg-card/60 px-4 pt-3">
            {SUGGESTIONS(selected).map((s) => (
              <button
                key={s}
                onClick={() => sendMessage(s)}
                disabled={sending}
                className="rounded-full border border-border/60 bg-background/40 px-2.5 py-1 text-[11px] text-muted-foreground transition hover:bg-muted hover:text-foreground disabled:opacity-50"
              >
                {s}
              </button>
            ))}
          </div>

          {/* Input */}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              sendMessage(input);
            }}
            className="flex items-center gap-2 border-t border-border/60 bg-card p-3"
          >
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Escribe tu pregunta…"
              className="flex-1 rounded-full border border-border bg-background px-4 py-2 text-sm text-foreground outline-none ring-ring transition focus:ring-2"
            />
            <button
              type="submit"
              disabled={!input.trim() || sending}
              className="flex h-9 w-9 items-center justify-center rounded-full bg-primary text-primary-foreground transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
              aria-label="Enviar"
            >
              <Send className="h-4 w-4" />
            </button>
          </form>
        </div>
      )}
    </>
  );
}

function Bubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} gap-2`}>
      {!isUser && (
        <div className="mt-0.5 flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-[image:var(--gradient-leaf)] text-white">
          <Bot className="h-3.5 w-3.5" />
        </div>
      )}
      <div
        className={`max-w-[80%] rounded-2xl px-3.5 py-2 text-sm leading-relaxed ${
          isUser
            ? "rounded-br-sm bg-primary text-primary-foreground"
            : message.status === "error"
              ? "rounded-bl-sm border border-destructive/40 bg-destructive/10 text-foreground"
              : "rounded-bl-sm bg-muted text-foreground"
        }`}
      >
        {message.status === "sending" ? (
          <span className="inline-flex gap-1">
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