'use client';

import { useEffect, useRef, useState } from 'react';
import { CloudRain, History, LayoutDashboard, Radio } from 'lucide-react';
import { Header } from './header';
import { KpiCards } from './kpi-cards';
import { MedellinMap } from './medellin-map';
import { CommuneInfo } from './commune-info';
import { RainfallChart } from './rainfall-chart';
import { RainMonitor } from './rain-monitor';
import { ScraperHealth } from './scraper-health';
import { ChatHistory } from './chat-history';
import { TeyvaChatWidget } from './teyva-chat';
import { fetchCommuneDetail, fetchRiskStats, type CommuneDetail, type CommuneFeature, type RiskStats } from '@/lib/api';
import type { View } from './header';

type CommuneProps = CommuneFeature['properties'];

export function Dashboard() {
  const [view, setView] = useState<View>('dashboard');
  const mapSectionRef = useRef<HTMLElement>(null);
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

  const navItems: { id: View; label: string; icon: React.ReactNode }[] = [
    { id: 'dashboard', label: 'Dashboard', icon: <LayoutDashboard size={16} /> },
    { id: 'rain', label: 'Monitor de Lluvia', icon: <CloudRain size={16} /> },
    { id: 'history', label: 'Historial de Chat', icon: <History size={16} /> },
    { id: 'system', label: 'Salud del Sistema', icon: <Radio size={16} /> },
  ];

  const renderNavButton = (item: (typeof navItems)[number], compact = false) => (
    <button
      key={item.id}
      onClick={() => setView(item.id)}
      className="press-scale"
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: compact ? '7px' : '10px',
        padding: compact ? '8px 13px' : '10px 14px',
        borderRadius: '12px',
        border: 'none',
        background: view === item.id ? 'oklch(0.91 0.025 65)' : 'transparent',
        color: view === item.id ? 'oklch(0.3 0.06 45)' : 'oklch(0.5 0.03 55)',
        fontSize: compact ? '13px' : '14px',
        fontWeight: view === item.id ? 700 : 500,
        cursor: 'pointer',
        textAlign: 'left',
        width: compact ? 'auto' : '100%',
        whiteSpace: 'nowrap',
        transition: 'all 0.15s',
        fontFamily: 'var(--font-sans)',
      }}
      onMouseEnter={(e) => { if (view !== item.id) e.currentTarget.style.background = 'oklch(0.94 0.018 70)'; }}
      onMouseLeave={(e) => { if (view !== item.id) e.currentTarget.style.background = 'transparent'; }}
    >
      <span style={{ display: 'flex', alignItems: 'center', lineHeight: 1 }}>{item.icon}</span>
      {item.label}
    </button>
  );

  return (
    <div style={{ minHeight: '100vh', background: 'oklch(0.96 0.014 75)', color: 'oklch(0.26 0.035 45)' }}>
      <Header activeView={view} onViewChange={setView} />

      {/* Nav horizontal en móvil/tablet */}
      <div
        className="teyva-scroll flex gap-1 overflow-x-auto px-4 py-2 lg:hidden"
        style={{ borderBottom: '1px solid var(--border)', background: 'var(--card)' }}
      >
        {navItems.map((item) => renderNavButton(item, true))}
      </div>

      <div style={{ display: 'flex', maxWidth: '1320px', margin: '0 auto' }}>

        {/* ── Sidebar (solo desktop) ── */}
        <aside
          className="hidden lg:flex"
          style={{
            width: '220px',
            flexShrink: 0,
            padding: '28px 14px 28px 0',
            flexDirection: 'column',
            gap: '4px',
            position: 'sticky',
            top: '66px',
            height: 'calc(100vh - 66px)',
          }}
        >
          {navItems.map((item) => renderNavButton(item))}
        </aside>

      <main className="px-4 md:px-7" style={{ flex: 1, padding: '26px 28px 90px', display: 'flex', flexDirection: 'column', gap: '22px', minWidth: 0 }}>

        {/* ===== HERO conversacional (solo en dashboard) ===== */}
        {view === 'dashboard' && <section
          className="anim-fade-up"
          style={{
            position: 'relative',
            overflow: 'hidden',
            borderRadius: '28px',
            background: 'linear-gradient(140deg, oklch(0.32 0.06 42) 0%, oklch(0.38 0.08 38) 55%, oklch(0.34 0.07 30) 100%)',
            padding: 'clamp(24px, 4vw, 44px)',
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
                  fontSize: 'clamp(27px, 3.4vw, 40px)',
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
                  onClick={() => mapSectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
                  className="press-scale"
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
                    transition: 'background 0.15s ease',
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = 'oklch(1 0 0 / 0.22)')}
                  onMouseLeave={(e) => (e.currentTarget.style.background = 'oklch(1 0 0 / 0.14)')}
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
            <section
              ref={mapSectionRef}
              className="anim-fade-up grid gap-[18px] xl:grid-cols-[1fr_400px]"
              style={{ alignItems: 'start', scrollMarginTop: '80px', animationDelay: '0.15s' }}
            >
              <div className="h-[420px] md:h-[600px]">
                <MedellinMap
                  onCommuneSelect={setSelectedCommune}
                  selectedCommuneId={selectedCommune ? String(selectedCommune.commune_id) : null}
                />
              </div>

              <div className="grid gap-[18px] md:grid-cols-2 xl:grid-cols-1">
                <div style={{ height: '360px' }}>
                  <CommuneInfo commune={selectedCommune} detail={communeDetail} loading={detailLoading} />
                </div>
                <div className="h-[360px] md:h-auto xl:h-[210px]">
                  <RainfallChart communeId={chartCommuneId} />
                </div>
              </div>
            </section>
          </>
        )}

        {view === 'rain' && <div className="anim-fade-up"><RainMonitor /></div>}
        {view === 'history' && <ChatHistory />}
        {view === 'system' && <div className="anim-fade-up"><ScraperHealth /></div>}

        <footer style={{ paddingTop: '8px', textAlign: 'center', fontSize: '12px', color: 'oklch(0.55 0.035 55)' }}>
          TEYVA · Sistema de análisis de riesgo territorial · Medellín, Antioquia
        </footer>
      </main>

      </div>{/* end flex wrapper */}

      <TeyvaChatWidget selectedCommune={selectedCommune} externalOpen={chatOpen} onOpenChange={setChatOpen} />
    </div>
  );
}
