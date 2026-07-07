'use client';

import { useEffect, useRef, useState } from 'react';
import {
  CalendarDays,
  CloudRain,
  Droplets,
  History,
  LayoutDashboard,
  MapPin,
  Radio,
} from 'lucide-react';
import { Header, type View } from './header';
import { KpiCards } from './kpi-cards';
import { MedellinMap } from './medellin-map';
import { BarriosMap } from './barrios-map';
import { MeshMap } from './mesh-map';
import { CommuneInfo } from './commune-info';
import { RainfallChart } from './rainfall-chart';
import { RainMonitor } from './rain-monitor';
import { ScraperHealth } from './scraper-health';
import { ChatHistory } from './chat-history';
import { ComunaProfile } from './comuna-profile';
import { EventsCalendar } from './events-calendar';
import { SeismicChart } from './seismic-chart';
import { SoilWaterHeatmap } from './soil-water-heatmap';
import { SnakeLineChart } from './snake-line-chart';
import { ModelFeaturesPanel } from './model-features-panel';
import { TeyvaChatWidget } from './teyva-chat';
import { fetchCommuneDetail, fetchCommunesCatalog, fetchRiskStats, type CommuneCatalogEntry, type CommuneDetail, type CommuneFeature, type RiskStats } from '@/lib/api';
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  useSidebar,
} from '@/components/ui/sidebar';

type CommuneProps = CommuneFeature['properties'];

// Fallback local si /api/geo/communes no responde. IDs CANÓNICOS (los mismos
// de risk_predictions/ml_features): corregimientos = 17-21, no los códigos
// oficiales 50-90 — con esos los endpoints devolvían siempre vacío.
const COMUNA_OPTIONS_FALLBACK: { id: string; nombre: string }[] = [
  { id: '1', nombre: 'Popular' }, { id: '2', nombre: 'Santa Cruz' }, { id: '3', nombre: 'Manrique' },
  { id: '4', nombre: 'Aranjuez' }, { id: '5', nombre: 'Castilla' }, { id: '6', nombre: 'Doce de Octubre' },
  { id: '7', nombre: 'Robledo' }, { id: '8', nombre: 'Villa Hermosa' }, { id: '9', nombre: 'Buenos Aires' },
  { id: '10', nombre: 'La Candelaria' }, { id: '11', nombre: 'Laureles-Estadio' }, { id: '12', nombre: 'La América' },
  { id: '13', nombre: 'San Javier' }, { id: '14', nombre: 'El Poblado' }, { id: '15', nombre: 'Guayabal' },
  { id: '16', nombre: 'Belén' }, { id: '17', nombre: 'Palmitas' }, { id: '18', nombre: 'San Cristóbal' },
  { id: '19', nombre: 'Altavista' }, { id: '20', nombre: 'San Antonio de Prado' }, { id: '21', nombre: 'Santa Elena' },
];

interface NavItem {
  id: View;
  label: string;
  icon: React.ReactNode;
}

const NAV_GROUPS: { label: string | null; items: NavItem[] }[] = [
  {
    label: null,
    items: [{ id: 'dashboard', label: 'Dashboard', icon: <LayoutDashboard /> }],
  },
  {
    label: 'Monitoreo',
    items: [
      { id: 'rain', label: 'Monitor de Lluvia', icon: <CloudRain /> },
      { id: 'events', label: 'Historial de Eventos', icon: <CalendarDays /> },
      { id: 'seismic', label: 'Actividad Sísmica', icon: <Radio /> },
      { id: 'decision', label: 'Monitor de Decisión', icon: <Droplets /> },
    ],
  },
  {
    label: 'Comunas',
    items: [{ id: 'comuna', label: 'Perfil de Comuna', icon: <MapPin /> }],
  },
  {
    label: 'Sistema',
    items: [
      { id: 'system', label: 'Salud del Sistema', icon: <Radio /> },
      { id: 'history', label: 'Historial de Chat', icon: <History /> },
    ],
  },
];

/** Logo + wordmark de la marca (vive en el header del sidebar). */
function BrandMark() {
  return (
    <div className="flex items-center gap-[11px] px-2 py-1.5">
      <div
        className="relative flex h-10 w-10 shrink-0 items-center justify-center"
        style={{
          borderRadius: '13px',
          background: 'var(--gradient-brand)',
          boxShadow: '0 6px 16px -6px oklch(0.55 0.13 40 / 0.5)',
        }}
      >
        <span
          style={{
            fontFamily: 'var(--font-display)',
            fontWeight: 800,
            fontSize: '20px',
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
            height: '12px',
            width: '12px',
            borderRadius: '99px',
            background: 'var(--gold)',
            border: '2.5px solid var(--sidebar)',
          }}
        />
      </div>
      <div className="min-w-0 group-data-[collapsible=icon]:hidden">
        <div
          style={{
            fontFamily: 'var(--font-display)',
            fontWeight: 700,
            fontSize: '21px',
            letterSpacing: '-0.02em',
            lineHeight: 1,
            color: 'var(--sidebar-foreground)',
          }}
        >
          TEYVA
        </div>
        <div
          className="truncate"
          style={{
            marginTop: '3px',
            fontSize: '9.5px',
            fontWeight: 600,
            textTransform: 'uppercase',
            letterSpacing: '0.14em',
            color: 'var(--muted-foreground)',
          }}
        >
          Riesgo de deslizamientos
        </div>
      </div>
    </div>
  );
}

/** Menú de navegación — vive dentro del provider para poder cerrar el sheet móvil. */
function NavMenu({ view, onNavigate }: { view: View; onNavigate: (v: View) => void }) {
  const { isMobile, setOpenMobile } = useSidebar();

  const go = (v: View) => {
    onNavigate(v);
    if (isMobile) setOpenMobile(false);
  };

  return (
    <>
      {NAV_GROUPS.map((group, gi) => (
        <SidebarGroup key={group.label ?? `g${gi}`}>
          {group.label && (
            <SidebarGroupLabel
              style={{ letterSpacing: '0.12em', textTransform: 'uppercase', fontSize: '10.5px' }}
            >
              {group.label}
            </SidebarGroupLabel>
          )}
          <SidebarGroupContent>
            <SidebarMenu>
              {group.items.map((item) => (
                <SidebarMenuItem key={item.id}>
                  <SidebarMenuButton
                    isActive={view === item.id}
                    onClick={() => go(item.id)}
                    tooltip={item.label}
                    style={{ fontWeight: view === item.id ? 700 : 500 }}
                  >
                    {item.icon}
                    <span>{item.label}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      ))}
    </>
  );
}

export function Dashboard() {
  const [view, setView] = useState<View>('dashboard');
  const mapSectionRef = useRef<HTMLElement>(null);
  const [selectedCommune, setSelectedCommune] = useState<CommuneProps | null>(null);
  const [communeDetail, setCommuneDetail] = useState<CommuneDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [stats, setStats] = useState<RiskStats | null>(null);
  const [chatOpen, setChatOpen] = useState(false);
  // Comuna mostrada en la vista de perfil (independiente de la selección del mapa)
  const [profileCommuneId, setProfileCommuneId] = useState<string | null>(null);
  // Capa activa del mapa: riesgo ML por comuna o amenaza oficial por barrio
  const [rightPanelTab, setRightPanelTab] = useState<'barrios' | 'mesh' | 'features' | null>(null);
  const [decisionCommuneId, setDecisionCommuneId] = useState<string>('1');
  const [comunaOptions, setComunaOptions] = useState<{ id: string; nombre: string }[]>(COMUNA_OPTIONS_FALLBACK);

  const chartCommuneId = selectedCommune ? String(selectedCommune.commune_id) : null;

  useEffect(() => {
    fetchRiskStats().then(setStats).catch(() => setStats(null));
    fetchCommunesCatalog()
      .then((communes: CommuneCatalogEntry[]) =>
        setComunaOptions(communes.map((c) => ({ id: c.id, nombre: c.nombre }))))
      .catch(() => { /* fallback local ya cargado */ });
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

  const openProfile = (communeId: string) => {
    setProfileCommuneId(communeId);
    setView('comuna');
  };

  return (
    <SidebarProvider
      style={{ background: 'var(--background)', color: 'var(--foreground)' } as React.CSSProperties}
    >
      <Sidebar collapsible="icon">
        <SidebarHeader style={{ borderBottom: '1px solid var(--sidebar-border)' }}>
          <BrandMark />
        </SidebarHeader>
        <SidebarContent>
          <NavMenu view={view} onNavigate={setView} />
        </SidebarContent>
        <SidebarFooter>
          <div
            className="px-2 pb-1 group-data-[collapsible=icon]:hidden"
            style={{ fontSize: '10.5px', color: 'var(--muted-foreground)', lineHeight: 1.5 }}
          >
            Medellín, Antioquia
            <br />
            Datos: SIATA · DAGRD · IDEAM
          </div>
        </SidebarFooter>
      </Sidebar>

      <SidebarInset style={{ background: 'var(--background)' }}>
        <Header activeView={view} />

        <main
          className="px-4 md:px-7"
          style={{ flex: 1, padding: '24px 28px 90px', display: 'flex', flexDirection: 'column', gap: '22px', minWidth: 0 }}
        >
          {/* ===== HERO conversacional (solo en dashboard) ===== */}
          {view === 'dashboard' && (
            <section
              className="anim-fade-up"
              style={{
                position: 'relative',
                overflow: 'hidden',
                borderRadius: '28px',
                background: 'var(--gradient-hero)',
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
                    'radial-gradient(circle at 88% 15%, oklch(0.82 0.14 78 / 0.35), transparent 42%), radial-gradient(circle at 8% 95%, oklch(0.6 0.15 258.9 / 0.45), transparent 45%)',
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
                        background: 'oklch(0.98 0.006 256.3)',
                        color: 'oklch(0.3 0.08 260)',
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
            </section>
          )}

          {view === 'dashboard' && (
            <>
              {/* ===== KPI CARDS ===== */}
              <KpiCards />

              {/* ===== MAPA + SIDEBAR DERECHO ===== */}
              <section
                ref={mapSectionRef}
                className="anim-fade-up grid gap-[18px]"
                style={{ gridTemplateColumns: rightPanelTab ? '1fr 380px' : '1fr', scrollMarginTop: '80px', animationDelay: '0.15s', transition: 'grid-template-columns 0.3s ease' }}
              >
                {/* MAPA PRINCIPAL (siempre comunas) */}
                <div>
                  <div className="mb-3 flex items-center gap-2 flex-wrap">
                    <button
                      onClick={() => setRightPanelTab(rightPanelTab === 'barrios' ? null : 'barrios')}
                      style={{
                        padding: '7px 14px',
                        borderRadius: '9px',
                        border: '1px solid var(--border)',
                        cursor: 'pointer',
                        fontSize: '12.5px',
                        fontWeight: 500,
                        background: rightPanelTab === 'barrios' ? 'var(--primary)' : 'var(--card)',
                        color: rightPanelTab === 'barrios' ? 'var(--primary-foreground)' : 'var(--muted-foreground)',
                        transition: 'all 0.15s ease',
                      }}
                    >
                      🏘️ Amenaza por Barrio
                    </button>
                    <button
                      onClick={() => setRightPanelTab(rightPanelTab === 'mesh' ? null : 'mesh')}
                      style={{
                        padding: '7px 14px',
                        borderRadius: '9px',
                        border: '1px solid var(--border)',
                        cursor: 'pointer',
                        fontSize: '12.5px',
                        fontWeight: 500,
                        background: rightPanelTab === 'mesh' ? 'var(--primary)' : 'var(--card)',
                        color: rightPanelTab === 'mesh' ? 'var(--primary-foreground)' : 'var(--muted-foreground)',
                        transition: 'all 0.15s ease',
                      }}
                    >
                      🔷 Mesh Maps
                    </button>
                    <button
                      onClick={() => setRightPanelTab(rightPanelTab === 'features' ? null : 'features')}
                      style={{
                        padding: '7px 14px',
                        borderRadius: '9px',
                        border: '1px solid var(--border)',
                        cursor: 'pointer',
                        fontSize: '12.5px',
                        fontWeight: 500,
                        background: rightPanelTab === 'features' ? 'var(--primary)' : 'var(--card)',
                        color: rightPanelTab === 'features' ? 'var(--primary-foreground)' : 'var(--muted-foreground)',
                        transition: 'all 0.15s ease',
                      }}
                    >
                      ⚙️ Features ML
                    </button>
                  </div>

                  <div className="h-[420px] md:h-[600px]">
                    <MedellinMap
                      onCommuneSelect={setSelectedCommune}
                      selectedCommuneId={selectedCommune ? String(selectedCommune.commune_id) : null}
                    />
                  </div>
                </div>

                {/* SIDEBAR DERECHO COLAPSABLE */}
                {rightPanelTab && (
                  <div
                    className="rounded-2xl border overflow-hidden flex flex-col"
                    style={{
                      borderColor: 'var(--border)',
                      background: 'var(--card)',
                      animation: 'slideInRight 0.3s ease',
                    }}
                  >
                    <div
                      style={{
                        padding: '14px 16px',
                        borderBottom: '1px solid var(--border)',
                        fontSize: '13px',
                        fontWeight: 700,
                        color: 'var(--foreground)',
                        background: 'var(--muted)',
                      }}
                    >
                      {rightPanelTab === 'barrios' ? '🏘️ Amenaza por Barrio (VM05)' : rightPanelTab === 'mesh' ? '🔷 Cuadrículas Mesh (JMA)' : '⚙️ Features del Modelo'}
                    </div>
                    <div style={{ flex: 1, overflow: 'auto', padding: '14px' }}>
                      {rightPanelTab === 'barrios' && <BarriosMap onOpenProfile={openProfile} />}
                      {rightPanelTab === 'mesh' && <MeshMap onOpenProfile={openProfile} />}
                      {rightPanelTab === 'features' && selectedCommune && (
                        <ModelFeaturesPanel
                          communeId={String(selectedCommune.commune_id)}
                          riskScore={selectedCommune.risk_score}
                          riskCategory={selectedCommune.risk_category || 'Sin datos'}
                        />
                      )}
                    </div>
                  </div>
                )}

                {/* PANEL INFO DERECHO (cuando NO hay sidebar) */}
                {!rightPanelTab && (
                  <div className="grid gap-[18px] md:grid-cols-2 xl:grid-cols-1">
                    <div style={{ height: '360px' }}>
                      <CommuneInfo
                        commune={selectedCommune}
                        detail={communeDetail}
                        loading={detailLoading}
                        onOpenProfile={openProfile}
                      />
                    </div>
                    <div className="h-[360px] md:h-auto xl:h-[210px]">
                      <RainfallChart communeId={chartCommuneId} />
                    </div>
                  </div>
                )}
              </section>

              <style>{`
                @keyframes slideInRight {
                  from { opacity: 0; transform: translateX(20px); }
                  to { opacity: 1; transform: translateX(0); }
                }
              `}</style>
            </>
          )}

          {view === 'rain' && <div className="anim-fade-up"><RainMonitor /></div>}
          {view === 'events' && <div className="anim-fade-up"><EventsCalendar onOpenProfile={openProfile} /></div>}
          {view === 'seismic' && (
            <div className="anim-fade-up">
              <div className="rounded-2xl border p-6" style={{ borderColor: 'var(--border)', background: 'var(--card)' }}>
                <div className="mb-4">
                  <h2 className="text-lg font-semibold text-foreground">Actividad Sísmica — Últimos 30 Días</h2>
                  <p className="text-xs text-muted-foreground mt-1">Magnitud máxima registrada y cantidad de eventos por día</p>
                </div>
                <SeismicChart />
              </div>
            </div>
          )}
          {view === 'decision' && (
            <div className="anim-fade-up">
              <div className="rounded-2xl border p-6" style={{ borderColor: 'var(--border)', background: 'var(--card)' }}>
                <div className="mb-4">
                  <h2 className="text-lg font-semibold text-foreground">Saturación del Suelo (SWI)</h2>
                  <p className="text-xs text-muted-foreground mt-1">
                    Estimación de agua retenida en el suelo por comuna, metodología JMA (tanque simplificado) — MVP sin calibrar con eventos históricos.
                  </p>
                </div>
                <SoilWaterHeatmap />
              </div>

              <div className="rounded-2xl border p-6 mt-4" style={{ borderColor: 'var(--border)', background: 'var(--card)' }}>
                <div className="mb-4 flex items-center justify-between flex-wrap gap-3">
                  <div>
                    <h2 className="text-lg font-semibold text-foreground">Snake Line — SWI × Lluvia Intensa</h2>
                    <p className="text-xs text-muted-foreground mt-1">
                      Cruza saturación del suelo y lluvia de la última hora contra una línea crítica de referencia.
                    </p>
                  </div>
                  <select
                    value={decisionCommuneId}
                    onChange={(e) => setDecisionCommuneId(e.target.value)}
                    style={{
                      padding: '8px 12px',
                      borderRadius: '10px',
                      border: '1px solid var(--border)',
                      background: 'var(--background)',
                      fontSize: '13px',
                      color: 'var(--foreground)',
                      cursor: 'pointer',
                    }}
                  >
                    {comunaOptions.map((c) => (
                      <option key={c.id} value={c.id}>{c.nombre}</option>
                    ))}
                  </select>
                </div>
                <SnakeLineChart communeId={decisionCommuneId} />
              </div>
            </div>
          )}
          {view === 'comuna' && (
            <div className="anim-fade-up">
              <ComunaProfile communeId={profileCommuneId} onSelectCommune={setProfileCommuneId} />
            </div>
          )}
          {view === 'history' && <ChatHistory />}
          {view === 'system' && <div className="anim-fade-up"><ScraperHealth /></div>}

          <footer style={{ paddingTop: '8px', textAlign: 'center', fontSize: '12px', color: 'var(--muted-foreground)' }}>
            TEYVA · Sistema de análisis de riesgo territorial · Medellín, Antioquia
          </footer>
        </main>
      </SidebarInset>

      <TeyvaChatWidget selectedCommune={selectedCommune} externalOpen={chatOpen} onOpenChange={setChatOpen} />
    </SidebarProvider>
  );
}
