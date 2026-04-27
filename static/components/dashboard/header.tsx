'use client';

import { useEffect, useState } from 'react';
import { useTheme } from 'next-themes';
import { Moon, Sun, Mountain, Activity } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { fetchBackendHealth } from '@/lib/api';

export function Header() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const [now, setNow] = useState('');
  const [systemOnline, setSystemOnline] = useState(false);

  useEffect(() => {
    setMounted(true);
    const update = () =>
      setNow(
        new Date().toLocaleString('es-CO', {
          dateStyle: 'medium',
          timeStyle: 'short',
        })
      );
    update();
    const id = setInterval(update, 30_000);
    return () => clearInterval(id);
  }, []);

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
    <header className="sticky top-0 z-40 border-b border-border/60 bg-background/80 backdrop-blur-xl">
      <div className="mx-auto flex max-w-[1600px] items-center justify-between gap-4 px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="relative flex h-11 w-11 items-center justify-center rounded-full bg-[image:var(--gradient-leaf)] shadow-[var(--shadow-soft)]">
            <Mountain className="h-5 w-5 text-white" strokeWidth={2.2} />
            <div className="absolute -bottom-1 -right-1 h-3 w-3 rounded-full bg-[var(--sun)] ring-2 ring-background" />
          </div>
          <div>
            <h1 className="font-display text-[32px] font-semibold leading-none tracking-tight text-foreground">TEYVA</h1>
            <p className="mt-1 text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
              Riesgo de deslizamientos · Medellín
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="hidden items-center gap-2 rounded-full border border-border/60 bg-card/60 px-3 py-1.5 text-xs md:flex">
            <span className="relative flex h-2 w-2">
              <span
                className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-60 ${systemOnline ? 'bg-[var(--leaf)]' : 'bg-red-500'}`}
              />
              <span
                className={`relative inline-flex h-2 w-2 rounded-full ${systemOnline ? 'bg-[var(--leaf)]' : 'bg-red-500'}`}
              />
            </span>
            <span className="font-medium text-foreground">
              {systemOnline ? 'Sistema en línea' : 'Sistema sin conexión'}
            </span>
            <span className="text-muted-foreground">·</span>
            <Activity className="h-3 w-3 text-muted-foreground" />
            <span className="text-muted-foreground">{mounted ? now : ''}</span>
          </div>
          <Button
            variant="outline"
            size="icon"
            className="rounded-full"
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            aria-label="Cambiar tema"
          >
            {mounted && theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </Button>
        </div>
      </div>
    </header>
  );
}
