'use client';

import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, CloudRain, Database, Layers, ShieldAlert, TrendingUp } from 'lucide-react';
import { fetchRiskStats, type RiskStats } from '@/lib/api';

export function KpiCards() {
  const [stats, setStats] = useState<RiskStats | null>(null);

  useEffect(() => {
    fetchRiskStats()
      .then(setStats)
      .catch(() => setStats(null));
  }, []);

  const kpi = useMemo(() => {
    if (!stats) {
      return {
        total: 'Sin datos',
        critical: 'Sin datos',
        high: 'Sin datos',
        events: 'Sin datos',
        trend: 'Sin datos',
      };
    }
    return {
      total: stats.total_comunas_monitoreadas,
      critical: stats.comunas_riesgo_critico,
      high: stats.comunas_riesgo_alto,
      events: stats.total_eventos_ultimos_30_dias,
      trend: stats.tendencia_riesgo_semana || 'Sin datos',
    };
  }, [stats]);

  const cards = [
    { label: 'Comunas monitoreadas', value: kpi.total, hint: 'cobertura total', icon: Layers, tone: 'emerald' },
    { label: 'Riesgo crítico', value: kpi.critical, hint: 'acción inmediata', icon: ShieldAlert, tone: 'rose' },
    { label: 'Riesgo alto', value: kpi.high, hint: 'vigilancia activa', icon: AlertTriangle, tone: 'amber' },
    { label: 'Eventos recientes', value: kpi.events, hint: 'últimos 30 días', icon: CloudRain, tone: 'orange' },
    { label: 'Tendencia semanal', value: kpi.trend, hint: 'últimos 7 días', icon: TrendingUp, tone: 'yellow' },
    { label: 'Fuente', value: 'Neon', hint: 'SQLAlchemy', icon: Database, tone: 'cyan' },
  ];

  const toneClasses: Record<string, string> = {
    emerald: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
    rose: 'bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300',
    amber: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
    orange: 'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300',
    yellow: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300',
    cyan: 'bg-cyan-100 text-cyan-700 dark:bg-cyan-900/40 dark:text-cyan-300',
  };

  return (
    <section className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6" aria-label="Resumen ejecutivo">
      {cards.map((card) => {
        const Icon = card.icon;
        return (
          <article
            key={card.label}
            className="group relative overflow-hidden rounded-2xl border border-border/60 bg-card p-4 shadow-[var(--shadow-soft)] transition-all hover:-translate-y-0.5 hover:shadow-[var(--shadow-elevated)]"
          >
            <div className={`flex h-9 w-9 items-center justify-center rounded-full ${toneClasses[card.tone]}`}>
              <Icon className="h-4 w-4" />
            </div>
            <div className="mt-4 font-display text-3xl font-semibold leading-none tracking-tight text-foreground">
              {card.value}
            </div>
            <div className="mt-2 text-sm font-medium text-foreground">{card.label}</div>
            <div className="mt-0.5 text-xs text-muted-foreground">{card.hint}</div>
            <div className="pointer-events-none absolute -bottom-12 -right-12 h-32 w-32 rounded-full bg-[image:var(--gradient-leaf)] opacity-[0.06] blur-2xl transition-opacity group-hover:opacity-[0.12]" />
          </article>
        );
      })}
    </section>
  );
}
