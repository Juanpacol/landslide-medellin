'use client';

import { useEffect, useState } from 'react';
import { fetchBackendHealth } from '@/lib/api';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { SidebarTrigger } from '@/components/ui/sidebar';

export type View = 'dashboard' | 'rain' | 'events' | 'seismic' | 'decision' | 'comuna' | 'history' | 'system';

export const VIEW_TITLES: Record<View, { title: string; crumb: string }> = {
  dashboard: { title: 'Dashboard', crumb: 'Resumen del valle' },
  rain: { title: 'Monitor de Lluvia', crumb: 'Monitoreo' },
  events: { title: 'Historial de Eventos', crumb: 'Monitoreo' },
  seismic: { title: 'Actividad Sísmica', crumb: 'Monitoreo' },
  decision: { title: 'Monitor de Decisión', crumb: 'Monitoreo' },
  comuna: { title: 'Perfil de Comuna', crumb: 'Comunas' },
  history: { title: 'Historial de Chat', crumb: 'Sistema' },
  system: { title: 'Salud del Sistema', crumb: 'Sistema' },
};

interface HeaderProps {
  activeView?: View;
}

export function Header({ activeView = 'dashboard' }: HeaderProps) {
  const [systemOnline, setSystemOnline] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      try {
        const ok = await fetchBackendHealth();
        if (!cancelled) setSystemOnline(ok);
      } catch {
        if (!cancelled) setSystemOnline(false);
      }
    };
    void check();
    const id = setInterval(() => void check(), 20_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const meta = VIEW_TITLES[activeView];

  return (
    <header
      className="sticky top-0 z-40 border-b"
      style={{
        borderColor: 'var(--border)',
        background: 'var(--glass-bg)',
        backdropFilter: 'blur(14px)',
      }}
    >
      <div className="flex items-center justify-between gap-4 px-4 py-[12px] md:px-6">
        {/* Trigger + breadcrumb */}
        <div className="flex min-w-0 items-center gap-3">
          <SidebarTrigger
            className="press-scale"
            style={{ color: 'var(--muted-foreground)' }}
          />
          <div className="min-w-0">
            <div
              style={{
                fontSize: '10.5px',
                fontWeight: 600,
                textTransform: 'uppercase',
                letterSpacing: '0.14em',
                color: 'var(--muted-foreground)',
              }}
            >
              {meta.crumb}
            </div>
            <div
              className="truncate"
              style={{
                fontFamily: 'var(--font-display)',
                fontWeight: 700,
                fontSize: '17px',
                letterSpacing: '-0.015em',
                lineHeight: 1.2,
                color: 'var(--foreground)',
              }}
            >
              {meta.title}
            </div>
          </div>
        </div>

        {/* Estado sistema + avatar */}
        <div className="flex items-center gap-3">
          <div
            className="hidden items-center gap-2 md:flex"
            style={{
              borderRadius: '99px',
              border: '1px solid var(--border)',
              background: 'var(--card)',
              padding: '7px 13px',
              fontSize: '12.5px',
            }}
          >
            <span className="relative flex h-2 w-2">
              <span
                className="absolute inline-flex h-full w-full rounded-full animate-teyva-ping"
                style={{ background: systemOnline ? 'var(--risk-bajo)' : 'var(--risk-critico)' }}
              />
              <span
                className="relative inline-flex h-2 w-2 rounded-full"
                style={{ background: systemOnline ? 'var(--risk-bajo)' : 'var(--risk-critico)' }}
              />
            </span>
            <span style={{ fontWeight: 600, color: 'var(--foreground)' }}>
              {systemOnline ? 'Sistema en línea' : 'Sin conexión'}
            </span>
          </div>

          <Avatar className="h-9 w-9">
            <AvatarFallback
              style={{
                background: 'oklch(0.9 0.035 256.3)',
                fontWeight: 700,
                fontSize: '13px',
                color: 'oklch(0.4 0.08 260)',
              }}
            >
              JP
            </AvatarFallback>
          </Avatar>
        </div>
      </div>
    </header>
  );
}
