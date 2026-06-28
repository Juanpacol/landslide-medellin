'use client';

import { useEffect, useState } from 'react';
import { fetchBackendHealth } from '@/lib/api';

type View = 'dashboard' | 'rain' | 'system';

interface HeaderProps {
  activeView?: View;
  onViewChange?: (view: View) => void;
}

export function Header({ activeView = 'dashboard', onViewChange }: HeaderProps) {
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

  return (
    <header
      className="sticky top-0 z-40 border-b"
      style={{
        borderColor: 'oklch(0.89 0.018 70)',
        background: 'oklch(0.97 0.012 75 / 0.85)',
        backdropFilter: 'blur(14px)',
      }}
    >
      <div className="mx-auto flex max-w-[1320px] items-center justify-between gap-4 px-7 py-[14px]">
        {/* Logo + wordmark */}
        <div className="flex items-center gap-[13px]">
          <div
            className="relative flex h-11 w-11 items-center justify-center"
            style={{
              borderRadius: '14px',
              background: 'var(--gradient-brand)',
              boxShadow: '0 6px 16px -6px oklch(0.55 0.13 40 / 0.5)',
            }}
          >
            <span
              style={{
                fontFamily: 'var(--font-display)',
                fontWeight: 800,
                fontSize: '22px',
                color: 'oklch(0.98 0.01 75)',
                lineHeight: 1,
              }}
            >
              T
            </span>
            <div
              className="absolute"
              style={{
                bottom: '-3px',
                right: '-3px',
                height: '13px',
                width: '13px',
                borderRadius: '99px',
                background: 'var(--gold)',
                border: '2.5px solid oklch(0.97 0.012 75)',
              }}
            />
          </div>

          <div>
            <div
              style={{
                fontFamily: 'var(--font-display)',
                fontWeight: 700,
                fontSize: '25px',
                letterSpacing: '-0.02em',
                lineHeight: 1,
                color: 'oklch(0.28 0.04 45)',
              }}
            >
              TEYVA
            </div>
            <div
              style={{
                marginTop: '3px',
                fontSize: '10.5px',
                fontWeight: 600,
                textTransform: 'uppercase',
                letterSpacing: '0.16em',
                color: 'oklch(0.55 0.04 55)',
              }}
            >
              Riesgo de deslizamientos · Medellín
            </div>
          </div>
        </div>

        {/* Nav */}
        <nav className="hidden items-center gap-1 md:flex">
          {([
            { id: 'dashboard' as View, label: 'Dashboard' },
            { id: 'rain' as View, label: '🌧 Monitor de Lluvia' },
            { id: 'system' as View, label: '📡 Sistema' },
          ] as const).map((item) => {
            const active = activeView === item.id;
            return (
              <button
                key={item.id}
                onClick={() => onViewChange?.(item.id)}
                style={{
                  padding: '8px 14px',
                  borderRadius: '10px',
                  fontSize: '14px',
                  fontWeight: active ? 600 : 500,
                  color: active ? 'oklch(0.32 0.04 45)' : 'oklch(0.5 0.03 55)',
                  background: active ? 'oklch(0.92 0.02 70)' : 'transparent',
                  cursor: 'pointer',
                  border: 'none',
                  fontFamily: 'var(--font-sans)',
                }}
              >
                {item.label}
              </button>
            );
          })}
        </nav>

        {/* Estado sistema + avatar */}
        <div className="flex items-center gap-3">
          <div
            className="hidden items-center gap-2 md:flex"
            style={{
              borderRadius: '99px',
              border: '1px solid oklch(0.89 0.018 70)',
              background: 'oklch(0.99 0.008 75)',
              padding: '7px 13px',
              fontSize: '12.5px',
            }}
          >
            <span className="relative flex h-2 w-2">
              <span
                className="absolute inline-flex h-full w-full rounded-full animate-teyva-ping"
                style={{ background: systemOnline ? 'oklch(0.64 0.13 150)' : 'oklch(0.6 0.18 30)' }}
              />
              <span
                className="relative inline-flex h-2 w-2 rounded-full"
                style={{ background: systemOnline ? 'oklch(0.64 0.13 150)' : 'oklch(0.6 0.18 30)' }}
              />
            </span>
            <span style={{ fontWeight: 600, color: 'oklch(0.3 0.04 45)' }}>
              {systemOnline ? 'Sistema en línea' : 'Sin conexión'}
            </span>
          </div>

          <div
            className="flex cursor-pointer items-center justify-center"
            style={{
              height: '40px',
              width: '40px',
              borderRadius: '99px',
              background: 'oklch(0.91 0.025 65)',
              fontWeight: 700,
              fontSize: '14px',
              color: 'oklch(0.4 0.06 50)',
            }}
          >
            JP
          </div>
        </div>
      </div>
    </header>
  );
}
