'use client';

import { useEffect, useMemo, useState } from 'react';
import { CloudRain, MapPin, Mountain, TriangleAlert } from 'lucide-react';
import { fetchRiskStats, fetchScraperHealth, type RiskStats, type ScraperHealthResponse } from '@/lib/api';

interface Kpi {
  label: string;
  value: string;
  icon: React.ReactNode;
  chipBg: string;
  chipFg: string;
  trend: string;
  trendColor: string;
}

/** Tarjeta de indicador — patrón compartido (label + icon chip + valor + trend). */
function StatCard({ kpi }: { kpi: Kpi }) {
  return (
    <div className="teyva-card hover-lift" style={{ padding: '20px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontSize: '12.5px', fontWeight: 600, color: 'var(--muted-foreground)' }}>
          {kpi.label}
        </span>
        <span className="teyva-icon-chip" style={{ background: kpi.chipBg, color: kpi.chipFg }}>
          {kpi.icon}
        </span>
      </div>
      <div
        style={{
          fontFamily: 'var(--font-display)',
          fontWeight: 700,
          fontSize: '32px',
          letterSpacing: '-0.02em',
          lineHeight: 1,
          marginTop: '16px',
          color: 'var(--foreground)',
        }}
      >
        {kpi.value}
      </div>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          marginTop: '10px',
          fontSize: '12.5px',
          color: kpi.trendColor,
        }}
      >
        {kpi.trend}
      </div>
    </div>
  );
}

export function KpiCards() {
  const [stats, setStats] = useState<RiskStats | null>(null);
  const [health, setHealth] = useState<ScraperHealthResponse | null>(null);

  useEffect(() => {
    fetchRiskStats().then(setStats).catch(() => setStats(null));
    fetchScraperHealth().then(setHealth).catch(() => setHealth(null));
  }, []);

  const kpis = useMemo<Kpi[]>(() => {
    const critico = stats?.comunas_riesgo_critico ?? '—';
    const alto = stats?.comunas_riesgo_alto ?? '—';
    const alertCount = typeof critico === 'number' && typeof alto === 'number' ? critico + alto : '—';

    return [
      {
        label: 'Nivel general del valle',
        value: stats ? (alertCount !== '—' && Number(alertCount) > 4 ? 'Alto' : 'Moderado') : '—',
        icon: <Mountain size={17} />,
        chipBg: 'oklch(0.94 0.04 75)',
        chipFg: 'oklch(0.55 0.1 60)',
        trend: '↑ Subiendo por lluvias',
        trendColor: 'oklch(0.6 0.15 50)',
      },
      {
        label: 'Comunas en alerta',
        value: String(alertCount),
        icon: <TriangleAlert size={17} />,
        chipBg: 'var(--risk-alto-soft)',
        chipFg: 'var(--risk-alto)',
        trend: stats ? `${critico} críticas · ${alto} altas` : 'Sin datos',
        trendColor: 'oklch(0.58 0.18 35)',
      },
      {
        label: 'Lluvia máx. 24h',
        value: stats?.max_precipitacion_24h != null ? `${stats.max_precipitacion_24h} mm` : '— mm',
        icon: <CloudRain size={17} />,
        chipBg: 'var(--water-soft)',
        chipFg: 'var(--water)',
        trend: 'Nororiente del valle',
        trendColor: 'var(--muted-foreground)',
      },
      {
        label: 'Eventos esta semana',
        value: stats?.total_eventos_ultimos_30_dias != null ? String(stats.total_eventos_ultimos_30_dias) : '—',
        icon: <MapPin size={17} />,
        chipBg: 'var(--risk-bajo-soft)',
        chipFg: 'var(--risk-bajo)',
        trend: 'Últimos 30 días',
        trendColor: 'var(--muted-foreground)',
      },
    ];
  }, [stats]);

  // Estado real de las fuentes (antes hardcodeado como ✓ siempre)
  const sources = useMemo(() => {
    const bySource = new Map(health?.sources.map((s) => [s.source, s.status]) ?? []);
    return [
      { key: 'siata', label: 'SIATA' },
      { key: 'ideam', label: 'IDEAM' },
      { key: 'dagrd', label: 'DAGRD' },
    ].map((s) => ({ ...s, status: bySource.get(s.key) ?? 'unknown' }));
  }, [health]);

  const allHealthy = health?.overall === 'healthy';

  return (
    <section
      className="anim-stagger grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5"
      aria-label="Indicadores clave"
    >
      {kpis.map((kpi) => (
        <StatCard key={kpi.label} kpi={kpi} />
      ))}

      {/* Tarjeta Estado del Sistema */}
      <div
        className="hover-lift"
        style={{
          padding: '20px',
          background: 'linear-gradient(135deg, oklch(0.88 0.03 256.3) 0%, oklch(0.85 0.045 258.9) 100%)',
          borderRadius: '20px',
          border: '1px solid oklch(0.78 0.05 258)',
          display: 'flex',
          flexDirection: 'column',
          gap: '14px',
          boxShadow: 'var(--shadow-sm)',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span
            style={{
              fontSize: '12.5px',
              fontWeight: 600,
              color: 'oklch(0.26 0.03 262)',
              textTransform: 'uppercase',
              letterSpacing: '0.5px',
            }}
          >
            Sistema
          </span>
          <div
            className="animate-teyva-ping"
            style={{
              width: '10px',
              height: '10px',
              borderRadius: '50%',
              background: allHealthy ? 'oklch(0.72 0.22 145)' : 'oklch(0.72 0.18 60)',
            }}
          />
        </div>
        <div style={{ fontSize: '12px', color: 'oklch(0.44 0.04 260)', lineHeight: 1.6, fontWeight: 500 }}>
          Scrapers:{' '}
          <strong style={{ color: 'oklch(0.26 0.03 262)', fontWeight: 700 }}>5 fuentes</strong>
          {' '}· Modelo:{' '}
          <strong style={{ color: 'oklch(0.26 0.03 262)', fontWeight: 700 }}>XGBoost</strong>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px' }}>
          {sources.map((src) => (
            <div
              key={src.key}
              style={{
                padding: '8px 6px',
                background: 'oklch(0.95 0.012 256.3)',
                borderRadius: '10px',
                textAlign: 'center',
                fontSize: '11px',
                fontWeight: 700,
                color:
                  src.status === 'healthy'
                    ? 'oklch(0.48 0.08 145)'
                    : src.status === 'unknown'
                      ? 'oklch(0.55 0.02 260)'
                      : 'oklch(0.55 0.15 40)',
              }}
            >
              {src.status === 'healthy' ? '✓' : src.status === 'unknown' ? '·' : '!'} {src.label}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
