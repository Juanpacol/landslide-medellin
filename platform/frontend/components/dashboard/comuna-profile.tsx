'use client';

import { useEffect, useMemo, useState } from 'react';
import { Activity, CalendarDays, ChevronRight, Droplets, Landmark, MapPin, Sparkles } from 'lucide-react';
import { Calendar } from '@/components/ui/calendar';
import { Progress } from '@/components/ui/progress';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  fetchCommuneDetail,
  fetchCommuneHistoryRaw,
  fetchLiveRainfall,
  fetchRiskExplanation,
  fetchSeismicEvents,
  normalizeRiskLevel,
  type CommuneDetail,
  type CommuneHistoryDay,
  type RainCommuneData,
  type RiskExplanationResponse,
  type SeismicEvent,
} from '@/lib/api';
import { ADVICE, LEVELS } from './commune-info';
import { AlertStateBadge } from './alert-state-badge';
import { DerivationPanel } from './derivation-panel';
import { EvacuationRoutesCard } from './evacuation-routes-card';

// ── helpers ────────────────────────────────────────────────────────────────────

const CHECKLIST: Record<string, string[]> = {
  Bajo: ['Monitoreo rutinario de fuentes', 'Revisar reportes semanales', 'Mantener canales comunitarios activos'],
  Medio: ['Vigilar evolución de lluvia', 'Revisar canales de drenaje', 'Informar a la comunidad'],
  Alto: ['Activar protocolos preventivos', 'Inspeccionar laderas inestables', 'Coordinar con el comité local de riesgo'],
  Crítico: ['Alerta máxima: considerar evacuación preventiva', 'Notificar al DAGRD de inmediato', 'Vigilancia continua de zonas vulnerables'],
};

function badgeClassFor(levelKey: string): string {
  if (levelKey === 'Crítico') return 'teyva-badge teyva-badge-danger';
  if (levelKey === 'Alto') return 'teyva-badge teyva-badge-warning';
  if (levelKey === 'Medio') return 'teyva-badge teyva-badge-warning';
  return 'teyva-badge teyva-badge-success';
}

/** Gauge circular SVG del score de riesgo (patrón "Vitals" de la referencia). */
function RiskGauge({ score, color }: { score: number | null; color: string }) {
  const pct = score !== null ? Math.round(score * 100) : null;
  const R = 52;
  const CIRC = 2 * Math.PI * R;
  const filled = pct !== null ? (pct / 100) * CIRC : 0;

  return (
    <div style={{ position: 'relative', width: '132px', height: '132px' }}>
      <svg width="132" height="132" viewBox="0 0 132 132" style={{ transform: 'rotate(-90deg)' }}>
        <circle cx="66" cy="66" r={R} fill="none" stroke="var(--muted)" strokeWidth="11" />
        <circle
          cx="66" cy="66" r={R} fill="none"
          stroke={color} strokeWidth="11" strokeLinecap="round"
          strokeDasharray={`${filled} ${CIRC - filled}`}
          style={{ transition: 'stroke-dasharray 0.6s cubic-bezier(0.22, 1, 0.36, 1)' }}
        />
      </svg>
      <div
        style={{
          position: 'absolute', inset: 0,
          display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
        }}
      >
        <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '30px', lineHeight: 1, color: 'var(--foreground)' }}>
          {pct !== null ? `${pct}%` : '—'}
        </span>
        <span style={{ fontSize: '10.5px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--muted-foreground)', marginTop: '4px' }}>
          Score ML
        </span>
      </div>
    </div>
  );
}

// ── selector (cuando no hay comuna elegida) ────────────────────────────────────

function CommuneSelector({
  comunas,
  onSelect,
}: {
  comunas: RainCommuneData[];
  onSelect: (id: string) => void;
}) {
  const sorted = useMemo(
    () => [...comunas].sort((a, b) => (b.risk_score ?? -1) - (a.risk_score ?? -1)),
    [comunas],
  );

  return (
    <div>
      <div style={{ marginBottom: '18px' }}>
        <h2 className="teyva-page-title">Perfil de Comuna</h2>
        <p className="teyva-page-subtitle">Elige una comuna para ver su expediente completo de riesgo.</p>
      </div>
      <div className="anim-stagger grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {sorted.map((c) => {
          const levelKey = c.risk_category ? normalizeRiskLevel(c.risk_category) : null;
          const level = levelKey ? LEVELS[levelKey] : null;
          return (
            <button
              key={c.commune_id}
              onClick={() => onSelect(c.commune_id)}
              className="teyva-card hover-lift press-scale"
              style={{
                padding: '16px 18px',
                textAlign: 'left',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: '10px',
              }}
            >
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--muted-foreground)' }}>
                  Comuna {c.commune_id}
                </div>
                <div
                  className="truncate"
                  style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '16.5px', color: 'var(--foreground)', marginTop: '3px' }}
                >
                  {c.nombre_comuna}
                </div>
                <div style={{ marginTop: '8px' }}>
                  {level ? (
                    <span className={badgeClassFor(levelKey!)}>
                      <span className="dot" />
                      {level.label}{c.risk_score !== null ? ` · ${Math.round(c.risk_score * 100)}%` : ''}
                    </span>
                  ) : (
                    <span className="teyva-badge teyva-badge-neutral">Sin datos</span>
                  )}
                </div>
              </div>
              <ChevronRight size={17} style={{ color: 'var(--muted-foreground)', flexShrink: 0 }} />
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ── página principal ───────────────────────────────────────────────────────────

interface ComunaProfileProps {
  communeId: string | null;
  onSelectCommune: (id: string | null) => void;
}

export function ComunaProfile({ communeId, onSelectCommune }: ComunaProfileProps) {
  const [comunas, setComunas] = useState<RainCommuneData[]>([]);
  const [detail, setDetail] = useState<CommuneDetail | null>(null);
  const [history, setHistory] = useState<CommuneHistoryDay[]>([]);
  const [explanation, setExplanation] = useState<RiskExplanationResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [calMonth, setCalMonth] = useState<Date>(new Date());
  const [seismic, setSeismic] = useState<SeismicEvent[]>([]);

  useEffect(() => {
    fetchLiveRainfall()
      .then((d) => setComunas(d.comunas))
      .catch(() => setComunas([]));
    fetchSeismicEvents()
      .then((d) => setSeismic(d.events))
      .catch(() => setSeismic([]));
  }, []);

  useEffect(() => {
    if (!communeId) {
      setDetail(null);
      setHistory([]);
      setExplanation(null);
      return;
    }
    setLoading(true);
    setExplanation(null);
    Promise.all([
      fetchCommuneDetail(communeId).catch(() => null),
      fetchCommuneHistoryRaw(communeId).catch(() => []),
    ])
      .then(([d, h]) => {
        setDetail(d);
        setHistory(h);
      })
      .finally(() => setLoading(false));
    fetchRiskExplanation(communeId).then(setExplanation).catch(() => setExplanation(null));
  }, [communeId]);

  if (!communeId) {
    return <CommuneSelector comunas={comunas} onSelect={onSelectCommune} />;
  }

  const live = comunas.find((c) => c.commune_id === communeId) ?? null;
  const levelKey = detail?.risk_level
    ? normalizeRiskLevel(detail.risk_level)
    : live?.risk_category
      ? normalizeRiskLevel(live.risk_category)
      : 'Bajo';
  const level = LEVELS[levelKey] ?? LEVELS['Bajo'];
  const score = detail?.risk_score ?? live?.risk_score ?? null;
  const nombre = detail?.nombre_comuna ?? live?.nombre_comuna ?? `Comuna ${communeId}`;

  // Días con eventos para marcar el calendario
  const eventDates = (detail?.historical_events ?? [])
    .map((e) => new Date(String(e.fecha).slice(0, 10) + 'T12:00:00'))
    .filter((d) => !Number.isNaN(d.getTime()));
  const eventsByDay = new Map<string, CommuneDetail['historical_events']>();
  for (const e of detail?.historical_events ?? []) {
    const k = String(e.fecha).slice(0, 10);
    eventsByDay.set(k, [...(eventsByDay.get(k) ?? []), e]);
  }

  const acum = live?.precip_acum_mm ?? 0;
  const umbral = live?.threshold_mm ?? 35;
  const rainPct = Math.min(100, Math.round((acum / umbral) * 100));

  const recentHistory = [...history].slice(-14).reverse();

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
      {/* ── Header del expediente ── */}
      <div className="teyva-card anim-fade-up" style={{ padding: '22px 24px' }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'flex-start', justifyContent: 'space-between', gap: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <div
              className="teyva-icon-chip"
              style={{ height: '52px', width: '52px', borderRadius: '16px', background: level.soft, color: level.color }}
            >
              <Landmark size={24} />
            </div>
            <div>
              <div style={{ fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.12em', color: 'var(--muted-foreground)' }}>
                Comuna {communeId}
              </div>
              <h2 className="teyva-page-title" style={{ fontSize: '28px', marginTop: '2px' }}>{nombre}</h2>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
            <span className={badgeClassFor(levelKey)} style={{ fontSize: '13px', padding: '6px 14px' }}>
              <span className="dot" />
              Riesgo {level.label}
            </span>
            <AlertStateBadge communeId={communeId} compact />
            <select
              value={communeId}
              onChange={(e) => onSelectCommune(e.target.value)}
              style={{
                padding: '8px 12px',
                borderRadius: '10px',
                border: '1px solid var(--border)',
                background: 'var(--card)',
                fontSize: '13px',
                color: 'var(--foreground)',
                cursor: 'pointer',
              }}
            >
              {comunas.map((c) => (
                <option key={c.commune_id} value={c.commune_id}>
                  {c.nombre_comuna}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Meta-badges */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginTop: '16px' }}>
          {detail?.is_zona_ladera && (
            <span className="teyva-badge teyva-badge-warning"><MapPin size={12} /> Zona de ladera</span>
          )}
          <span className="teyva-badge teyva-badge-info"><Droplets size={12} /> Umbral {umbral.toFixed(0)} mm</span>
          <span className="teyva-badge teyva-badge-neutral">
            <CalendarDays size={12} />
            {detail?.predicted_at
              ? `Predicción: ${new Date(detail.predicted_at).toLocaleString('es-CO', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}`
              : 'Sin predicción reciente'}
          </span>
        </div>
      </div>

      {/* ── Fila "vitals": gauge + lluvia vs umbral + checklist ── */}
      <div className="anim-stagger grid grid-cols-1 gap-[18px] md:grid-cols-2 xl:grid-cols-4">
        {/* Gauge del score */}
        <div className="teyva-card" style={{ padding: '20px 22px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '10px' }}>
          <div style={{ alignSelf: 'flex-start', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: 'var(--muted-foreground)' }}>
            Índice de riesgo
          </div>
          {loading ? <Skeleton className="h-[132px] w-[132px] rounded-full" /> : <RiskGauge score={score} color={level.color} />}
          <p style={{ fontSize: '12px', color: 'var(--muted-foreground)', textAlign: 'center', margin: 0 }}>
            Probabilidad de deslizamiento a 7 días (XGBoost)
          </p>
        </div>

        {/* Lluvia hoy vs umbral */}
        <div className="teyva-card" style={{ padding: '20px 22px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <div style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: 'var(--muted-foreground)' }}>
            Lluvia hoy vs umbral
          </div>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '34px', lineHeight: 1, color: 'var(--foreground)' }}>
            {acum.toFixed(1)}<span style={{ fontSize: '17px', fontWeight: 500 }}> mm</span>
          </div>
          <div>
            <Progress
              value={rainPct}
              className="h-[9px]"
              style={{ background: 'var(--muted)' }}
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '7px', fontSize: '12px', color: 'var(--muted-foreground)' }}>
              <span>0 mm</span>
              <span style={{ fontWeight: 700, color: rainPct >= 100 ? 'var(--risk-critico)' : 'var(--foreground)' }}>
                {rainPct}% del umbral
              </span>
              <span>{umbral.toFixed(0)} mm</span>
            </div>
          </div>
          <div style={{ fontSize: '12.5px', color: 'var(--muted-foreground)', display: 'flex', gap: '14px' }}>
            <span>7 días: <strong style={{ color: 'var(--foreground)' }}>{detail?.rainfall_last_7d_total ?? '—'} mm</strong></span>
            <span>30 días: <strong style={{ color: 'var(--foreground)' }}>{detail?.rainfall_last_30d_total ?? '—'} mm</strong></span>
          </div>
        </div>

        {/* Checklist de acciones */}
        <div className="teyva-card" style={{ padding: '20px 22px' }}>
          <div style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: 'var(--muted-foreground)', marginBottom: '12px' }}>
            Acciones recomendadas
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '9px' }}>
            {(CHECKLIST[levelKey] ?? CHECKLIST['Bajo']).map((item, i) => (
              <div key={i} style={{ display: 'flex', gap: '10px', alignItems: 'flex-start' }}>
                <span
                  style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    height: '20px', width: '20px', borderRadius: '99px', flexShrink: 0,
                    background: level.soft, color: level.color,
                    fontSize: '11px', fontWeight: 700, marginTop: '1px',
                  }}
                >
                  {i + 1}
                </span>
                <span style={{ fontSize: '13px', lineHeight: 1.45, color: 'var(--foreground)' }}>{item}</span>
              </div>
            ))}
          </div>
          <p style={{ fontSize: '12px', color: 'var(--muted-foreground)', marginTop: '12px', marginBottom: 0 }}>
            {ADVICE[levelKey] ?? ADVICE['Bajo']}
          </p>
        </div>

        {/* Actividad sísmica reciente (red SIATA — valle completo) */}
        <div className="teyva-card" style={{ padding: '20px 22px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '7px', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: 'var(--muted-foreground)', marginBottom: '12px' }}>
            <Activity size={13} />
            Actividad sísmica
          </div>
          {seismic.length === 0 ? (
            <p style={{ fontSize: '12.5px', color: 'var(--muted-foreground)', margin: 0 }}>
              Sin sismos registrados por la red SIATA recientemente.
            </p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '9px' }}>
              {seismic.slice(0, 3).map((s, i) => {
                const strong = (s.magnitude ?? 0) >= 4;
                return (
                  <div
                    key={i}
                    style={{
                      display: 'flex', alignItems: 'center', gap: '10px',
                      padding: '9px 11px', borderRadius: '11px', background: 'var(--muted)',
                    }}
                  >
                    <span
                      style={{
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        height: '34px', width: '34px', borderRadius: '10px', flexShrink: 0,
                        background: strong ? 'var(--risk-alto-soft)' : 'var(--risk-bajo-soft)',
                        color: strong ? 'var(--risk-alto)' : 'var(--risk-bajo)',
                        fontSize: '12px', fontWeight: 800,
                      }}
                    >
                      M{s.magnitude ?? '?'}
                    </span>
                    <div style={{ minWidth: 0 }}>
                      <div className="truncate" style={{ fontSize: '12.5px', fontWeight: 700, color: 'var(--foreground)' }}>
                        {(s.epicenter_label ?? 'Sismo').replace(/^Sismo en /, '')}
                      </div>
                      <div style={{ fontSize: '11.5px', color: 'var(--muted-foreground)', marginTop: '1px' }}>
                        {s.depth_km != null ? `${s.depth_km.toFixed(0)} km prof. · ` : ''}
                        {s.event_local_at
                          ? new Date(s.event_local_at).toLocaleDateString('es-CO', { day: '2-digit', month: 'short' })
                          : 's/f'}
                      </div>
                    </div>
                  </div>
                );
              })}
              <p style={{ fontSize: '11px', color: 'var(--muted-foreground)', margin: '3px 0 0' }}>
                Red de sismógrafos SIATA · registro para todo el valle
              </p>
            </div>
          )}
        </div>
      </div>

      <EvacuationRoutesCard communeId={communeId} />

      {/* ── Calendario de eventos + tabla de historia ── */}
      <div className="grid grid-cols-1 gap-[18px] xl:grid-cols-[auto_1fr]">
        {/* Calendario + eventos */}
        <div className="teyva-card anim-fade-up" style={{ padding: '20px 22px' }}>
          <div style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: 'var(--muted-foreground)', marginBottom: '10px' }}>
            Calendario de eventos
          </div>
          <Calendar
            mode="single"
            month={calMonth}
            onMonthChange={setCalMonth}
            modifiers={{ event: eventDates }}
            modifiersClassNames={{ event: 'teyva-day-event' }}
            className="p-0"
          />
          <div style={{ marginTop: '14px', borderTop: '1px solid var(--border)', paddingTop: '14px' }}>
            <div style={{ fontSize: '12px', fontWeight: 700, color: 'var(--foreground)', marginBottom: '8px' }}>
              Eventos registrados ({detail?.historical_events?.length ?? 0})
            </div>
            {(detail?.historical_events ?? []).length === 0 ? (
              <p style={{ fontSize: '12.5px', color: 'var(--muted-foreground)', margin: 0 }}>
                Sin eventos DAGRD registrados para esta comuna.
              </p>
            ) : (
              <div className="teyva-scroll" style={{ display: 'flex', flexDirection: 'column', gap: '7px', maxHeight: '180px', overflowY: 'auto' }}>
                {(detail?.historical_events ?? []).slice(0, 20).map((e) => (
                  <div
                    key={e.id}
                    style={{
                      display: 'flex', alignItems: 'center', gap: '9px',
                      padding: '8px 11px', borderRadius: '10px', background: 'var(--muted)',
                      fontSize: '12.5px',
                    }}
                  >
                    <span style={{ height: '7px', width: '7px', borderRadius: '99px', background: 'var(--risk-alto)', flexShrink: 0 }} />
                    <span style={{ fontWeight: 600, color: 'var(--foreground)', whiteSpace: 'nowrap' }}>
                      {String(e.fecha).slice(0, 10)}
                    </span>
                    <span className="truncate" style={{ color: 'var(--muted-foreground)' }}>
                      {e.tipo_emergencia}{e.barrio ? ` · ${e.barrio}` : ''}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Tabla de historia diaria */}
        <div className="teyva-card anim-fade-up" style={{ padding: '20px 22px', minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
            <div style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: 'var(--muted-foreground)' }}>
              Historia diaria · últimos 14 días
            </div>
          </div>
          {loading ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-9 w-full" />)}
            </div>
          ) : recentHistory.length === 0 ? (
            <p style={{ fontSize: '13px', color: 'var(--muted-foreground)' }}>Sin historial disponible.</p>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Fecha</TableHead>
                    <TableHead className="text-right">Lluvia (mm)</TableHead>
                    <TableHead className="text-right">Eventos</TableHead>
                    <TableHead>Riesgo</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {recentHistory.map((d) => {
                    const dayLevel = d.risk_category && d.risk_category !== 'Sin datos'
                      ? normalizeRiskLevel(d.risk_category)
                      : null;
                    return (
                      <TableRow key={d.date}>
                        <TableCell style={{ fontWeight: 600 }}>
                          {new Date(d.date + 'T12:00:00').toLocaleDateString('es-CO', { weekday: 'short', day: '2-digit', month: 'short' })}
                        </TableCell>
                        <TableCell className="text-right" style={{ color: d.rainfall > 0 ? 'var(--water)' : 'var(--muted-foreground)', fontWeight: d.rainfall > 0 ? 700 : 400 }}>
                          {d.rainfall.toFixed(1)}
                        </TableCell>
                        <TableCell className="text-right" style={{ color: d.landslides > 0 ? 'var(--risk-critico)' : 'var(--muted-foreground)', fontWeight: d.landslides > 0 ? 700 : 400 }}>
                          {d.landslides}
                        </TableCell>
                        <TableCell>
                          {dayLevel ? (
                            <span className={badgeClassFor(dayLevel)} style={{ fontSize: '11px', padding: '3px 9px' }}>
                              {LEVELS[dayLevel].label}
                            </span>
                          ) : (
                            <span style={{ fontSize: '12px', color: 'var(--muted-foreground)' }}>—</span>
                          )}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          )}
        </div>
      </div>

      {/* ── Explicación IA ── */}
      {(explanation?.explanation || detail?.model_explanation) && (
        <div
          className="anim-fade-up"
          style={{
            borderRadius: '20px',
            border: `1px solid ${level.color}44`,
            padding: '18px 22px',
            background: level.soft,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '7px', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'oklch(0.45 0.04 50)' }}>
              <Sparkles size={13} />
              Análisis de riesgo · IA
            </div>
            {explanation?.generated_by && (
              <span className="teyva-badge teyva-badge-neutral" style={{ fontSize: '10.5px', padding: '3px 9px' }}>
                {explanation.generated_by === 'template'
                  ? 'Análisis automático'
                  : explanation.generated_by === 'derivation'
                    ? '🔗 Derivación neuro-simbólica'
                    : '✦ Generado por IA'}
              </span>
            )}
          </div>
          <p style={{ fontSize: '13.5px', lineHeight: 1.6, color: 'oklch(0.35 0.04 48)', margin: 0 }}>
            {explanation?.explanation ?? detail?.model_explanation}
          </p>
        </div>
      )}

      {/* ── Derivación neuro-simbólica ── */}
      <div className="teyva-card anim-fade-up" style={{ padding: '20px 22px' }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '7px',
            fontSize: '11px',
            fontWeight: 700,
            textTransform: 'uppercase',
            letterSpacing: '0.1em',
            color: 'var(--muted-foreground)',
            marginBottom: '12px',
          }}
        >
          Derivación del score
        </div>
        <DerivationPanel communeId={communeId} />
      </div>
    </div>
  );
}
