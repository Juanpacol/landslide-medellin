'use client';

import { useEffect, useMemo, useState } from 'react';
import { fetchRiskStats, type RiskStats } from '@/lib/api';

const SHADOW = '0 1px 2px oklch(0.5 0.05 50 / 0.04), 0 10px 26px -16px oklch(0.5 0.06 45 / 0.3)';

export function KpiCards() {
  const [stats, setStats] = useState<RiskStats | null>(null);

  useEffect(() => {
    fetchRiskStats()
      .then(setStats)
      .catch(() => setStats(null));
  }, []);

  const kpis = useMemo(() => {
    const critico = stats?.comunas_riesgo_critico ?? '—';
    const alto = stats?.comunas_riesgo_alto ?? '—';
    const alertCount = typeof critico === 'number' && typeof alto === 'number' ? critico + alto : '—';

    return [
      {
        label: 'Nivel general del valle',
        value: stats ? (alertCount !== '—' && Number(alertCount) > 4 ? 'Alto' : 'Moderado') : '—',
        icon: '⛰️',
        iconBg: 'oklch(0.94 0.04 75)',
        trend: '↑ Subiendo por lluvias',
        trendColor: 'oklch(0.6 0.15 50)',
      },
      {
        label: 'Comunas en alerta',
        value: String(alertCount),
        icon: '⚠️',
        iconBg: 'oklch(0.94 0.05 55)',
        trend: stats ? `${critico} críticas · ${alto} altas` : 'Sin datos',
        trendColor: 'oklch(0.58 0.18 35)',
      },
      {
        label: 'Lluvia máx. 24h',
        value: stats?.max_precipitacion_24h != null ? `${stats.max_precipitacion_24h} mm` : '— mm',
        icon: '🌧️',
        iconBg: 'oklch(0.93 0.04 230)',
        trend: 'Nororiente del valle',
        trendColor: 'oklch(0.52 0.035 55)',
      },
      {
        label: 'Eventos esta semana',
        value: stats?.total_eventos_ultimos_30_dias != null ? String(stats.total_eventos_ultimos_30_dias) : '—',
        icon: '📍',
        iconBg: 'oklch(0.94 0.03 145)',
        trend: 'Últimos 30 días',
        trendColor: 'oklch(0.52 0.035 55)',
      },
    ];
  }, [stats]);

  return (
    <section
      className="anim-stagger grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5"
      aria-label="Indicadores clave"
    >
      {kpis.map((kpi) => (
        <div
          key={kpi.label}
          className="hover-lift"
          style={{
            borderRadius: '20px',
            border: '1px solid oklch(0.9 0.018 70)',
            background: 'oklch(0.99 0.008 75)',
            padding: '20px',
            boxShadow: SHADOW,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontSize: '12.5px', fontWeight: 600, color: 'oklch(0.52 0.035 55)' }}>
              {kpi.label}
            </span>
            <span
              style={{
                height: '34px',
                width: '34px',
                borderRadius: '11px',
                background: kpi.iconBg,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '16px',
                flexShrink: 0,
              }}
            >
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
              color: 'oklch(0.28 0.04 45)',
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
      ))}

      {/* Tarjeta Estado del Sistema */}
      <div
        className="hover-lift"
        style={{
          padding: '20px',
          background: 'linear-gradient(135deg, oklch(0.88 0.022 35) 0%, oklch(0.86 0.028 25) 100%)',
          borderRadius: '20px',
          border: '1px solid oklch(0.78 0.035 38)',
          display: 'flex',
          flexDirection: 'column',
          gap: '14px',
          boxShadow: SHADOW,
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span
            style={{
              fontSize: '12.5px',
              fontWeight: 600,
              color: 'oklch(0.26 0.04 38)',
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
              background: 'oklch(0.72 0.22 145)',
            }}
          />
        </div>
        <div style={{ fontSize: '12px', color: 'oklch(0.48 0.04 48)', lineHeight: 1.6, fontWeight: 500 }}>
          Scrapers:{' '}
          <strong style={{ color: 'oklch(0.28 0.04 40)', fontWeight: 700 }}>4 fuentes</strong>
          {' '}· Modelo:{' '}
          <strong style={{ color: 'oklch(0.28 0.04 40)', fontWeight: 700 }}>XGBoost</strong>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px' }}>
          {['SIATA', 'IDEAM', 'DAGRD'].map((src) => (
            <div
              key={src}
              style={{
                padding: '8px 6px',
                background: 'oklch(0.95 0.015 70)',
                borderRadius: '10px',
                textAlign: 'center',
                fontSize: '11px',
                fontWeight: 700,
                color: 'oklch(0.48 0.08 145)',
              }}
            >
              ✓ {src}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
