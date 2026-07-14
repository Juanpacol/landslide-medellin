'use client';

import { useEffect, useState } from 'react';
import { fetchAlertState, type AlertStateEntry } from '@/lib/api';

const STATE_STYLE: Record<AlertStateEntry['state'], { bg: string; fg: string; border: string; label: string; pulse: boolean }> = {
  VERDE: { bg: 'oklch(0.94 0.06 145)', fg: 'oklch(0.35 0.1 145)', border: 'oklch(0.7 0.13 145)', label: 'Monitoreo', pulse: false },
  AMARILLO: { bg: 'oklch(0.94 0.08 90)', fg: 'oklch(0.4 0.1 80)', border: 'oklch(0.75 0.14 85)', label: 'Alistamiento', pulse: true },
  ROJO: { bg: 'oklch(0.93 0.08 25)', fg: 'oklch(0.4 0.15 25)', border: 'oklch(0.62 0.22 25)', label: 'Evacuación', pulse: true },
};

interface AlertStateBadgeProps {
  communeId: string;
  compact?: boolean;
}

export function AlertStateBadge({ communeId, compact = false }: AlertStateBadgeProps) {
  const [state, setState] = useState<AlertStateEntry | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const data = await fetchAlertState(communeId);
        if (!cancelled) setState(data);
      } catch {
        if (!cancelled) setState(null);
      }
    };
    void load();
    const id = setInterval(load, 5 * 60_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [communeId]);

  if (!state) {
    return (
      <div
        className="inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-medium"
        style={{ background: 'var(--muted)', color: 'var(--muted-foreground)' }}
      >
        Sin datos
      </div>
    );
  }

  const style = STATE_STYLE[state.state];

  return (
    <div
      className="inline-flex flex-col gap-1 rounded-2xl px-3.5 py-2.5"
      style={{ background: style.bg, border: `1px solid ${style.border}` }}
    >
      <div className="flex items-center gap-2">
        <span
          className={style.pulse ? 'teyva-alert-dot-pulse' : ''}
          style={{
            height: '9px',
            width: '9px',
            borderRadius: '99px',
            background: style.border,
            flexShrink: 0,
          }}
        />
        <span className="text-sm font-bold" style={{ color: style.fg }}>
          {state.state} · {style.label}
        </span>
      </div>
      {!compact && (
        <>
          <div className="text-xs" style={{ color: style.fg, opacity: 0.85 }}>
            {state.action}
          </div>
          <div className="flex gap-3 text-[11px] mt-0.5" style={{ color: style.fg, opacity: 0.75 }}>
            <span>Lluvia: {(state.rainfall_pct * 100).toFixed(0)}% umbral</span>
            <span>Antecedente: {(state.antecedent_pct * 100).toFixed(0)}%</span>
          </div>
        </>
      )}
      <style jsx>{`
        .teyva-alert-dot-pulse {
          animation: teyva-alert-pulse 1.6s ease-in-out infinite;
        }
        @keyframes teyva-alert-pulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.4; transform: scale(1.3); }
        }
      `}</style>
    </div>
  );
}
