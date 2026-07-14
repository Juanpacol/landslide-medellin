'use client';

import { useEffect, useMemo, useState } from 'react';
import { Activity, BellRing, CalendarDays, CloudRain, Landmark, TriangleAlert } from 'lucide-react';
import { Calendar } from '@/components/ui/calendar';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import {
  fetchAlertLog,
  fetchAlerts,
  fetchCommuneDetail,
  fetchLiveRainfall,
  fetchSeismicEvents,
  normalizeRiskLevel,
  type Alert,
  type AlertLogEntry,
  type CommuneDetail,
  type RainCommuneData,
  type SeismicEvent,
} from '@/lib/api';
import { LEVELS } from './commune-info';

type DayEvent =
  | { kind: 'dagrd'; date: string; commune: string; label: string; detail: string }
  | { kind: 'alerta'; date: string; commune: string; label: string; detail: string }
  | { kind: 'sismo'; date: string; commune: string; label: string; detail: string };

function dayKey(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

interface EventsCalendarProps {
  onOpenProfile?: (communeId: string) => void;
}

export function EventsCalendar({ onOpenProfile }: EventsCalendarProps) {
  const [comunas, setComunas] = useState<RainCommuneData[]>([]);
  const [communeFilter, setCommuneFilter] = useState<string>('all');
  const [alertLog, setAlertLog] = useState<AlertLogEntry[]>([]);
  const [activeAlerts, setActiveAlerts] = useState<Alert[]>([]);
  const [seismic, setSeismic] = useState<SeismicEvent[]>([]);
  const [details, setDetails] = useState<Map<string, CommuneDetail>>(new Map());
  const [loading, setLoading] = useState(true);
  const [month, setMonth] = useState<Date>(new Date());
  const [selectedDay, setSelectedDay] = useState<Date | undefined>(undefined);
  const [sheetOpen, setSheetOpen] = useState(false);

  // Carga base: comunas, log de alertas y alertas activas
  useEffect(() => {
    Promise.all([
      fetchLiveRainfall().catch(() => null),
      fetchAlertLog().catch(() => ({ logs: [] as AlertLogEntry[] })),
      fetchAlerts().catch(() => [] as Alert[]),
      fetchSeismicEvents().catch(() => ({ events: [] as SeismicEvent[], total: 0 })),
    ])
      .then(([live, log, alerts, quakes]) => {
        setComunas(live?.comunas ?? []);
        setAlertLog(log.logs);
        setActiveAlerts(alerts);
        setSeismic(quakes.events);
      })
      .finally(() => setLoading(false));
  }, []);

  // Eventos DAGRD: del detalle de la comuna filtrada, o de las comunas en alerta
  // (traer las 21 sería excesivo; alertas activas ≈ donde hay eventos relevantes).
  useEffect(() => {
    const ids =
      communeFilter !== 'all'
        ? [communeFilter]
        : [...new Set(activeAlerts.map((a) => a.commune_id))].slice(0, 8);
    if (ids.length === 0) return;

    let cancelled = false;
    void Promise.all(
      ids
        .filter((id) => !details.has(id))
        .map((id) => fetchCommuneDetail(id).then((d) => [id, d] as const).catch(() => null)),
    ).then((pairs) => {
      if (cancelled) return;
      const next = new Map(details);
      for (const p of pairs) {
        if (p) next.set(p[0], p[1]);
      }
      if (next.size !== details.size) setDetails(next);
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [communeFilter, activeAlerts]);

  // Índice: día → eventos
  const seismicRef = seismic;
  const eventsByDay = useMemo(() => {
    const map = new Map<string, DayEvent[]>();
    const push = (k: string, e: DayEvent) => map.set(k, [...(map.get(k) ?? []), e]);

    for (const [id, d] of details) {
      if (communeFilter !== 'all' && id !== communeFilter) continue;
      for (const e of d.historical_events ?? []) {
        const k = String(e.fecha).slice(0, 10);
        if (!/^\d{4}-\d{2}-\d{2}$/.test(k)) continue;
        push(k, {
          kind: 'dagrd',
          date: k,
          commune: d.nombre_comuna,
          label: e.tipo_emergencia || 'Evento DAGRD',
          detail: e.barrio ? `Barrio ${e.barrio}` : d.nombre_comuna,
        });
      }
    }

    for (const a of alertLog) {
      if (!a.triggered_at) continue;
      if (communeFilter !== 'all' && a.commune_id !== communeFilter) continue;
      const k = String(a.triggered_at).slice(0, 10);
      push(k, {
        kind: 'alerta',
        date: k,
        commune: a.nombre_comuna,
        label: `Alerta de lluvia (${a.status ?? 'enviada'})`,
        detail: `${a.precip_acum_mm?.toFixed(1) ?? '?'} mm acumulados · umbral ${a.threshold_mm?.toFixed(0) ?? '?'} mm`,
      });
    }

    // Sismos: registro del valle completo (no dependen del filtro de comuna).
    for (const q of seismicRef) {
      if (!q.event_local_at) continue;
      const k = String(q.event_local_at).slice(0, 10);
      if (!/^\d{4}-\d{2}-\d{2}$/.test(k)) continue;
      push(k, {
        kind: 'sismo',
        date: k,
        commune: 'Valle de Aburrá',
        label: (q.epicenter_label ?? 'Sismo registrado') + (q.magnitude != null ? ` (M${q.magnitude})` : ''),
        detail: q.depth_km != null ? `${q.depth_km.toFixed(0)} km de profundidad` : 'profundidad s/d',
      });
    }

    return map;
  }, [details, alertLog, communeFilter, seismicRef]);

  const dagrdDates = useMemo(
    () =>
      [...eventsByDay.entries()]
        .filter(([, evs]) => evs.some((e) => e.kind === 'dagrd'))
        .map(([k]) => new Date(k + 'T12:00:00')),
    [eventsByDay],
  );
  const alertDates = useMemo(
    () =>
      [...eventsByDay.entries()]
        .filter(([, evs]) => evs.some((e) => e.kind === 'alerta'))
        .map(([k]) => new Date(k + 'T12:00:00')),
    [eventsByDay],
  );
  const sismoDates = useMemo(
    () =>
      [...eventsByDay.entries()]
        .filter(([, evs]) => evs.some((e) => e.kind === 'sismo'))
        .map(([k]) => new Date(k + 'T12:00:00')),
    [eventsByDay],
  );

  const totalEvents = [...eventsByDay.values()].reduce((acc, evs) => acc + evs.length, 0);
  const selectedEvents = selectedDay ? eventsByDay.get(dayKey(selectedDay)) ?? [] : [];

  const onDayClick = (day: Date | undefined) => {
    setSelectedDay(day);
    if (day && (eventsByDay.get(dayKey(day))?.length ?? 0) > 0) {
      setSheetOpen(true);
    }
  };

  // Resumen del mes visible (lista lateral, patrón "agenda")
  const monthEvents = useMemo(() => {
    const mk = `${month.getFullYear()}-${String(month.getMonth() + 1).padStart(2, '0')}`;
    return [...eventsByDay.entries()]
      .filter(([k]) => k.startsWith(mk))
      .sort(([a], [b]) => b.localeCompare(a))
      .flatMap(([, evs]) => evs);
  }, [eventsByDay, month]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
      {/* Header */}
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: '12px' }}>
        <div>
          <h2 className="teyva-page-title">Historial de Eventos</h2>
          <p className="teyva-page-subtitle">
            Emergencias DAGRD y alertas de lluvia en el tiempo · clic en un día marcado para ver el detalle
          </p>
        </div>
        <select
          value={communeFilter}
          onChange={(e) => setCommuneFilter(e.target.value)}
          style={{
            padding: '9px 13px',
            borderRadius: '10px',
            border: '1px solid var(--border)',
            background: 'var(--card)',
            fontSize: '13px',
            color: 'var(--foreground)',
            cursor: 'pointer',
          }}
        >
          <option value="all">Todas las comunas (en alerta)</option>
          {comunas.map((c) => (
            <option key={c.commune_id} value={c.commune_id}>
              {c.nombre_comuna}
            </option>
          ))}
        </select>
      </div>

      {/* Leyenda + contadores */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
        <span className="teyva-badge teyva-badge-warning"><TriangleAlert size={12} /> {dagrdDates.length} días con eventos DAGRD</span>
        <span className="teyva-badge teyva-badge-danger"><BellRing size={12} /> {alertDates.length} días con alertas de lluvia</span>
        <span className="teyva-badge teyva-badge-info"><Activity size={12} /> {sismoDates.length} días con sismos</span>
        <span className="teyva-badge teyva-badge-neutral"><CalendarDays size={12} /> {totalEvents} registros en total</span>
      </div>

      <div className="grid grid-cols-1 gap-[18px] xl:grid-cols-[auto_1fr]">
        {/* Calendario */}
        <div className="teyva-card anim-fade-up" style={{ padding: '20px 22px' }}>
          {loading ? (
            <div style={{ padding: '40px 20px', textAlign: 'center', fontSize: '13px', color: 'var(--muted-foreground)' }}>
              Cargando eventos…
            </div>
          ) : (
            <Calendar
              mode="single"
              selected={selectedDay}
              onSelect={onDayClick}
              month={month}
              onMonthChange={setMonth}
              modifiers={{ event: dagrdDates, alert: alertDates, sismo: sismoDates }}
              modifiersClassNames={{ event: 'teyva-day-event', alert: 'teyva-day-alert', sismo: 'teyva-day-sismo' }}
              className="p-0 [--cell-size:2.6rem]"
            />
          )}
          <div style={{ display: 'flex', gap: '14px', marginTop: '14px', paddingTop: '12px', borderTop: '1px solid var(--border)', fontSize: '12px', color: 'var(--muted-foreground)' }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ height: '6px', width: '6px', borderRadius: '99px', background: 'var(--risk-alto)' }} /> Evento DAGRD
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ height: '6px', width: '6px', borderRadius: '99px', background: 'var(--risk-critico)' }} /> Alerta de lluvia
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ height: '3px', width: '12px', borderRadius: '99px', background: 'var(--info)' }} /> Sismo
            </span>
          </div>
        </div>

        {/* Agenda del mes */}
        <div className="teyva-card anim-fade-up" style={{ padding: '20px 22px', minWidth: 0 }}>
          <div style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: 'var(--muted-foreground)', marginBottom: '12px' }}>
            Registros de {month.toLocaleDateString('es-CO', { month: 'long', year: 'numeric' })}
          </div>
          {monthEvents.length === 0 ? (
            <div style={{ padding: '30px 0', textAlign: 'center' }}>
              <CloudRain size={28} style={{ color: 'var(--muted-foreground)', margin: '0 auto 10px' }} />
              <p style={{ fontSize: '13px', color: 'var(--muted-foreground)', margin: 0 }}>
                Sin eventos ni alertas registradas este mes
                {communeFilter === 'all' ? ' en las comunas en alerta' : ''}.
              </p>
              <p style={{ fontSize: '12px', color: 'var(--muted-foreground)', marginTop: '6px' }}>
                Navega a otros meses con las flechas del calendario.
              </p>
            </div>
          ) : (
            <div className="teyva-scroll" style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '420px', overflowY: 'auto' }}>
              {monthEvents.slice(0, 60).map((e, i) => (
                <div
                  key={`${e.date}-${i}`}
                  style={{
                    display: 'flex', alignItems: 'center', gap: '11px',
                    padding: '10px 13px', borderRadius: '12px', background: 'var(--muted)',
                  }}
                >
                  <span
                    className="teyva-icon-chip"
                    style={{
                      height: '32px', width: '32px', borderRadius: '9px',
                      background:
                        e.kind === 'dagrd' ? 'var(--risk-alto-soft)'
                        : e.kind === 'sismo' ? 'var(--info-soft)'
                        : 'var(--risk-critico-soft)',
                      color:
                        e.kind === 'dagrd' ? 'var(--risk-alto)'
                        : e.kind === 'sismo' ? 'var(--info)'
                        : 'var(--risk-critico)',
                    }}
                  >
                    {e.kind === 'dagrd' ? <TriangleAlert size={15} /> : e.kind === 'sismo' ? <Activity size={15} /> : <BellRing size={15} />}
                  </span>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div className="truncate" style={{ fontSize: '13px', fontWeight: 700, color: 'var(--foreground)' }}>
                      {e.label}
                    </div>
                    <div className="truncate" style={{ fontSize: '12px', color: 'var(--muted-foreground)', marginTop: '1px' }}>
                      {e.date} · {e.commune} · {e.detail}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Sheet de detalle del día */}
      <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
        <SheetContent side="right" style={{ background: 'var(--card)' }}>
          <SheetHeader>
            <SheetTitle style={{ fontFamily: 'var(--font-display)', letterSpacing: '-0.01em' }}>
              {selectedDay?.toLocaleDateString('es-CO', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}
            </SheetTitle>
            <SheetDescription>
              {selectedEvents.length} registro{selectedEvents.length === 1 ? '' : 's'} este día
            </SheetDescription>
          </SheetHeader>
          <div className="teyva-scroll" style={{ display: 'flex', flexDirection: 'column', gap: '10px', padding: '0 16px 20px', overflowY: 'auto' }}>
            {selectedEvents.map((e, i) => (
              <div
                key={i}
                style={{
                  borderRadius: '14px',
                  border: '1px solid var(--border)',
                  padding: '13px 15px',
                  background: 'var(--background)',
                }}
              >
                <span
                  className={
                    e.kind === 'dagrd' ? 'teyva-badge teyva-badge-warning'
                    : e.kind === 'sismo' ? 'teyva-badge teyva-badge-info'
                    : 'teyva-badge teyva-badge-danger'
                  }
                >
                  {e.kind === 'dagrd' ? <TriangleAlert size={12} /> : e.kind === 'sismo' ? <Activity size={12} /> : <BellRing size={12} />}
                  {e.kind === 'dagrd' ? 'Evento DAGRD' : e.kind === 'sismo' ? 'Sismo (red SIATA)' : 'Alerta de lluvia'}
                </span>
                <div style={{ fontSize: '14px', fontWeight: 700, color: 'var(--foreground)', marginTop: '9px' }}>
                  {e.label}
                </div>
                <div style={{ fontSize: '12.5px', color: 'var(--muted-foreground)', marginTop: '3px' }}>
                  {e.detail}
                </div>
                <button
                  onClick={() => {
                    const c = comunas.find((x) => x.nombre_comuna === e.commune);
                    if (c && onOpenProfile) {
                      setSheetOpen(false);
                      onOpenProfile(c.commune_id);
                    }
                  }}
                  className="press-scale"
                  style={{
                    marginTop: '10px', display: 'inline-flex', alignItems: 'center', gap: '6px',
                    padding: '6px 12px', borderRadius: '9px', border: '1px solid var(--border)',
                    background: 'var(--card)', fontSize: '12px', fontWeight: 600,
                    color: 'var(--foreground)', cursor: 'pointer',
                  }}
                >
                  <Landmark size={12} /> {e.commune}
                </button>
              </div>
            ))}
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}
