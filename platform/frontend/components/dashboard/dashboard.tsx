'use client';

import { useEffect, useState } from 'react';
import { Header } from './header';
import { KpiCards } from './kpi-cards';
import { MedellinMap } from './medellin-map';
import { CommuneInfo } from './commune-info';
import { RainfallChart } from './rainfall-chart';
import { RainMonitor } from './rain-monitor';
import { ScraperHealth } from './scraper-health';
import { TeyvaChatWidget } from './teyva-chat';
import { fetchCommuneDetail, fetchRiskStats, type CommuneDetail, type CommuneFeature, type RiskStats } from '@/lib/api';

type View = 'dashboard' | 'rain' | 'system';

type CommuneProps = CommuneFeature['properties'];

export function Dashboard() {
  const [view, setView] = useState<View>('dashboard');
  const [selectedCommune, setSelectedCommune] = useState<CommuneProps | null>(null);
  const [communeDetail, setCommuneDetail] = useState<CommuneDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [stats, setStats] = useState<RiskStats | null>(null);
  const [chatOpen, setChatOpen] = useState(false);

  const chartCommuneId = selectedCommune ? String(selectedCommune.commune_id) : null;

  useEffect(() => {
    fetchRiskStats().then(setStats).catch(() => setStats(null));
  }, []);

  useEffect(() => {
    if (!chartCommuneId) {
      setCommuneDetail(null);
      return;
    }
    setDetailLoading(true);
    fetchCommuneDetail(chartCommuneId)
      .then((data) => setCommuneDetail(data))
      .catch(() => setCommuneDetail(null))
      .finally(() => setDetailLoading(false));
  }, [chartCommuneId]);

  const alertCount =
    stats
      ? (stats.comunas_riesgo_critico ?? 0) + (stats.comunas_riesgo_alto ?? 0)
      : null;

  const heroTitle =
    alertCount !== null
      ? alertCount > 0
        ? `Hoy hay ${alertCount} comunas que vale la pena vigilar.`
        : 'El valle está estable hoy. Buen momento para revisar el histórico.'
      : 'Cargando el estado del valle…';

  const navItems: { id: View; label: string; icon: string }[] = [
    { id: 'dashboard', label: 'Dashboard', icon: '◉' },
    { id: 'rain', label: 'Monitor de Lluvia', icon: '🌧' },
    { id: 'system', label: 'Salud del Sistema', icon: '📡' },
  ];

  return (
    <div style={{ minHeight: '100vh', background: 'oklch(0.96 0.014 75)', color: 'oklch(0.26 0.035 45)' }}>
      <Header activeView={view} onViewChange={setView} />

      <div style={{ display: 'flex', maxWidth: '1320px', margin: '0 auto' }}>

        {/* ── Sidebar ── */}
        <aside style={{
          width: '220px',
          flexShrink: 0,
          padding: '28px 14px 28px 0',
          display: 'flex',
          flexDirection: 'column',
          gap: '4px',
          position: 'sticky',
          top: '66px',
          height: 'calc(100vh - 66px)',
        }}>
          {navItems.map((item) => (
            <button
              key={item.id}
              onClick={() => setView(item.id)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
                padding: '10px 14px',
                borderRadius: '12px',
                border: 'none',
                background: view === item.id ? 'oklch(0.91 0.025 65)' : 'transparent',
                color: view === item.id ? 'oklch(0.3 0.06 45)' : 'oklch(0.5 0.03 55)',
                fontSize: '14px',
                fontWeight: view === item.id ? 700 : 500,
                cursor: 'pointer',
                textAlign: 'left',
                width: '100%',
                transition: 'all 0.15s',
                fontFamily: 'var(--font-sans)',
              }}
              onMouseEnter={(e) => { if (view !== item.id) e.currentTarget.style.background = 'oklch(0.94 0.018 70)'; }}
              onMouseLeave={(e) => { if (view !== item.id) e.currentTarget.style.background = 'transparent'; }}
            >
              <span style={{ fontSize: '16px', lineHeight: 1 }}>{item.icon}</span>
              {item.label}
            </button>
          ))}
        </aside>

      <main style={{ flex: 1, padding: '26px 28px 90px', display: 'flex', flexDirection: 'column', gap: '22px', minWidth: 0 }}>

        {/* ===== HERO conversacional (solo en dashboard) ===== */}
        {view === 'dashboard' && <section
          style={{
            position: 'relative',
            overflow: 'hidden',
            borderRadius: '28px',
            background: 'linear-gradient(140deg, oklch(0.32 0.06 42) 0%, oklch(0.38 0.08 38) 55%, oklch(0.34 0.07 30) 100%)',
            padding: '40px 44px',
            color: 'oklch(0.97 0.015 80)',
          }}
        >
          {/* Destellos decorativos */}
          <div
            aria-hidden
            style={{
              position: 'absolute',
              inset: 0,
              opacity: 0.5,
              background:
                'radial-gradient(circle at 88% 15%, oklch(0.82 0.14 78 / 0.35), transparent 42%), radial-gradient(circle at 8% 95%, oklch(0.7 0.13 40 / 0.4), transparent 45%)',
              pointerEvents: 'none',
            }}
          />

          <div style={{ position: 'relative', display: 'flex', flexWrap: 'wrap', alignItems: 'flex-end', justifyContent: 'space-between', gap: '28px' }}>
            <div style={{ maxWidth: '600px' }}>
              {/* Eyebrow */}
              <div
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '8px',
                  borderRadius: '99px',
                  background: 'oklch(1 0 0 / 0.14)',
                  padding: '6px 13px',
                  fontSize: '11.5px',
                  fontWeight: 600,
                  textTransform: 'uppercase',
                  letterSpacing: '0.14em',
                }}
              >
                <span style={{ height: '6px', width: '6px', borderRadius: '99px', background: 'oklch(0.82 0.14 78)' }} />
                Hoy · Medellín, Antioquia
              </div>

              {/* Título */}
              <h1
                style={{
                  fontFamily: 'var(--font-display)',
                  fontWeight: 700,
                  fontSize: '40px',
                  lineHeight: 1.08,
                  letterSpacing: '-0.025em',
                  marginTop: '18px',
                }}
              >
                {heroTitle}
              </h1>
              <p style={{ marginTop: '14px', fontSize: '16px', lineHeight: 1.55, color: 'oklch(1 0 0 / 0.82)', maxWidth: '520px' }}>
                Datos en tiempo real de lluvias, eventos y predicciones del modelo para que actúes a tiempo, sin tecnicismos.
              </p>

              {/* CTAs */}
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', marginTop: '26px' }}>
                <button
                  onClick={() => setChatOpen(true)}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '8px',
                    border: 'none',
                    cursor: 'pointer',
                    borderRadius: '13px',
                    background: 'oklch(0.98 0.012 80)',
                    color: 'oklch(0.3 0.06 45)',
                    padding: '13px 20px',
                    fontFamily: 'var(--font-sans)',
                    fontSize: '14.5px',
                    fontWeight: 700,
                    transition: 'transform 0.15s ease',
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.transform = 'translateY(-1px)')}
                  onMouseLeave={(e) => (e.currentTarget.style.transform = 'none')}
                >
                  💬 Hablar con Teyva
                </button>
                <button
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '8px',
                    cursor: 'pointer',
                    borderRadius: '13px',
                    background: 'oklch(1 0 0 / 0.14)',
                    border: '1px solid oklch(1 0 0 / 0.22)',
                    color: 'oklch(0.98 0.01 80)',
                    padding: '13px 20px',
                    fontFamily: 'var(--font-sans)',
                    fontSize: '14.5px',
                    fontWeight: 600,
                  }}
                >
                  Ver comunas en alerta
                </button>
              </div>
            </div>

            {/* Mini stats del hero */}
            <div style={{ display: 'flex', gap: '14px', flexShrink: 0 }}>
              <div
                style={{
                  borderRadius: '20px',
                  background: 'oklch(1 0 0 / 0.12)',
                  border: '1px solid oklch(1 0 0 / 0.16)',
                  padding: '18px 20px',
                  minWidth: '130px',
                  backdropFilter: 'blur(6px)',
                }}
              >
                <div style={{ fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'oklch(1 0 0 / 0.7)' }}>
                  Lluvia 24h
                </div>
                <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '34px', lineHeight: 1, marginTop: '8px' }}>
                  {stats?.max_precipitacion_24h != null ? stats.max_precipitacion_24h : '—'}
                  <span style={{ fontSize: '16px', fontWeight: 500 }}> mm</span>
                </div>
                <div style={{ fontSize: '12px', marginTop: '6px', color: 'oklch(0.85 0.13 80)' }}>↑ Nororiente</div>
              </div>
              <div
                style={{
                  borderRadius: '20px',
                  background: 'oklch(1 0 0 / 0.12)',
                  border: '1px solid oklch(1 0 0 / 0.16)',
                  padding: '18px 20px',
                  minWidth: '130px',
                  backdropFilter: 'blur(6px)',
                }}
              >
                <div style={{ fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'oklch(1 0 0 / 0.7)' }}>
                  En alerta
                </div>
                <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '34px', lineHeight: 1, marginTop: '8px' }}>
                  {alertCount ?? '—'}
                  <span style={{ fontSize: '16px', fontWeight: 500 }}> comunas</span>
                </div>
                <div style={{ fontSize: '12px', marginTop: '6px', color: 'oklch(0.8 0.13 40)' }}>Requieren atención</div>
              </div>
            </div>
          </div>
        </section>}

        {view === 'dashboard' && (
          <>
            {/* ===== KPI CARDS ===== */}
            <KpiCards />

            {/* ===== MAPA + PANEL LATERAL ===== */}
            <section style={{ display: 'grid', gridTemplateColumns: '1fr 400px', gap: '18px', alignItems: 'start' }}>
              <div style={{ height: '600px' }}>
                <MedellinMap
                  onCommuneSelect={setSelectedCommune}
                  selectedCommuneId={selectedCommune ? String(selectedCommune.commune_id) : null}
                />
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
                <div style={{ height: '360px' }}>
                  <CommuneInfo commune={selectedCommune} detail={communeDetail} loading={detailLoading} />
                </div>
                <div style={{ height: '210px' }}>
                  <RainfallChart communeId={chartCommuneId} />
                </div>
              </div>
            </section>
          </>
        )}

        {view === 'rain' && <RainMonitor />}
        {view === 'system' && <ScraperHealth />}

        <footer style={{ paddingTop: '8px', textAlign: 'center', fontSize: '12px', color: 'oklch(0.55 0.035 55)' }}>
          TEYVA · Sistema de análisis de riesgo territorial · Medellín, Antioquia
        </footer>
      </main>

      </div>{/* end flex wrapper */}

      <TeyvaChatWidget selectedCommune={selectedCommune} externalOpen={chatOpen} onOpenChange={setChatOpen} />
    </div>
  );
}
