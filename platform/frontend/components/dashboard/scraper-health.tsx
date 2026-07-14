'use client';

import { Fragment, useEffect, useState } from 'react';
import { Building2, ChevronDown, CloudRain, Mountain, RefreshCcw, Thermometer } from 'lucide-react';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  fetchScraperHealth,
  fetchScraperTimeline,
  type ScraperHealthResponse,
  type ScraperRunEntry,
  type ScraperSourceHealth,
  type ScraperTimelineResponse,
} from '@/lib/api';

// ── helpers ────────────────────────────────────────────────────────────────────

const SOURCE_LABELS: Record<string, string> = {
  siata: 'SIATA',
  dagrd: 'DAGRD',
  ideam: 'IDEAM',
  medellin_datos: 'Medellín Datos',
};

const SOURCE_DESCS: Record<string, string> = {
  siata: 'Lluvia en tiempo real · cada 30 min',
  dagrd: 'Eventos de deslizamiento · cada 1 h',
  ideam: 'Datos meteorológicos · cada 6 h',
  medellin_datos: 'Datos municipales · cada 24 h',
};

const SOURCE_ICONS: Record<string, React.ReactNode> = {
  siata: <CloudRain size={17} />,
  dagrd: <Mountain size={17} />,
  ideam: <Thermometer size={17} />,
  medellin_datos: <Building2 size={17} />,
};

const SOURCE_CHIP: Record<string, { bg: string; fg: string }> = {
  siata: { bg: 'var(--water-soft)', fg: 'var(--water)' },
  dagrd: { bg: 'var(--risk-alto-soft)', fg: 'var(--risk-alto)' },
  ideam: { bg: 'var(--risk-medio-soft)', fg: 'oklch(0.55 0.12 70)' },
  medellin_datos: { bg: 'var(--risk-bajo-soft)', fg: 'var(--risk-bajo)' },
};

function statusBadgeClass(s: string): string {
  if (s === 'healthy') return 'teyva-badge teyva-badge-success';
  if (s === 'warning') return 'teyva-badge teyva-badge-warning';
  if (s === 'critical') return 'teyva-badge teyva-badge-danger';
  return 'teyva-badge teyva-badge-neutral';
}

function statusLabel(s: string): string {
  if (s === 'healthy') return 'Activo';
  if (s === 'warning') return 'Alerta';
  if (s === 'critical') return 'Caído';
  return 'Sin datos';
}

function relativeTime(iso: string | null): string {
  if (!iso) return '—';
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 2) return 'hace un momento';
  if (mins < 60) return `hace ${mins} min`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `hace ${hrs} h`;
  const days = Math.floor(hrs / 24);
  return `hace ${days} día${days > 1 ? 's' : ''}`;
}

function lagColor(lag: number | null, interval: number): string {
  if (lag === null) return 'var(--muted-foreground)';
  if (lag <= interval * 1.5) return 'var(--badge-success-fg)';
  if (lag <= interval * 3) return 'var(--badge-warning-fg)';
  return 'var(--badge-danger-fg)';
}

function runBadgeClass(status: string): string {
  if (status === 'ok' || status === 'completed' || status === 'success') return 'teyva-badge teyva-badge-success';
  if (status === 'started') return 'teyva-badge teyva-badge-warning';
  return 'teyva-badge teyva-badge-danger';
}

// ── sub-components ─────────────────────────────────────────────────────────────

function RunTimeline({ runs }: { runs: ScraperRunEntry[] }) {
  if (!runs.length) {
    return <p style={{ fontSize: '12px', color: 'var(--muted-foreground)', fontStyle: 'italic', margin: 0 }}>Sin registros aún</p>;
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
      {runs.map((r) => (
        <div
          key={r.id}
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr auto',
            alignItems: 'center',
            gap: '8px',
            padding: '7px 11px',
            borderRadius: '9px',
            background: 'var(--card)',
            border: '1px solid var(--border)',
            fontSize: '12px',
          }}
        >
          <span style={{ color: 'var(--foreground)' }}>
            {r.run_started_at
              ? new Date(r.run_started_at).toLocaleString('es-CO', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
              : '—'}
            {r.records_valid != null && (
              <span style={{ marginLeft: '8px', color: 'var(--muted-foreground)' }}>
                {r.records_valid} válidos
              </span>
            )}
          </span>
          <span className={runBadgeClass(r.status)} style={{ fontSize: '11px', padding: '2px 8px' }}>
            {r.status}
          </span>
        </div>
      ))}
    </div>
  );
}

function OverallBadge({ overall }: { overall: 'healthy' | 'warning' | 'critical' }) {
  const label = overall === 'healthy' ? 'Todo en orden' : overall === 'warning' ? 'Requiere atención' : 'Intervención necesaria';
  return (
    <span className={statusBadgeClass(overall)} style={{ fontSize: '13.5px', padding: '8px 15px' }}>
      <span className="dot" /> {label}
    </span>
  );
}

// ── main component ─────────────────────────────────────────────────────────────

export function ScraperHealth() {
  const [health, setHealth] = useState<ScraperHealthResponse | null>(null);
  const [timeline, setTimeline] = useState<ScraperTimelineResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  const load = async () => {
    try {
      const [h, t] = await Promise.all([fetchScraperHealth(), fetchScraperTimeline()]);
      setHealth(h);
      setTimeline(t);
      setLastRefresh(new Date());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error de conexión');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    const id = setInterval(() => void load(), 60_000);
    return () => clearInterval(id);
  }, []);

  if (loading && !health) {
    return (
      <div style={{ textAlign: 'center', padding: '60px 0', color: 'var(--muted-foreground)' }}>
        Cargando estado del sistema…
      </div>
    );
  }

  if (error && !health) {
    return (
      <div style={{ textAlign: 'center', padding: '60px 0', color: 'var(--badge-danger-fg)' }}>
        {error}
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
      {/* Title + overall badge */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <h2 className="teyva-page-title">Salud del Sistema</h2>
          <p className="teyva-page-subtitle">
            Estado de los scrapers de datos en tiempo real
            {lastRefresh && (
              <> · actualizado {lastRefresh.toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit' })} · refresco cada 60 s</>
            )}
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {health && <OverallBadge overall={health.overall} />}
          <button
            onClick={() => { setLoading(true); void load(); }}
            className="press-scale"
            style={{
              display: 'flex', alignItems: 'center', gap: '6px',
              padding: '8px 14px', borderRadius: '10px',
              border: '1px solid var(--border)',
              background: 'var(--card)',
              fontSize: '13px', color: 'var(--foreground)',
              cursor: 'pointer', fontWeight: 500,
            }}
          >
            <RefreshCcw size={13} /> Actualizar
          </button>
        </div>
      </div>

      {/* Summary chips */}
      {health && (
        <div className="anim-stagger grid grid-cols-2 gap-3 lg:grid-cols-4">
          {health.sources.map((src) => {
            const chip = SOURCE_CHIP[src.source] ?? { bg: 'var(--muted)', fg: 'var(--muted-foreground)' };
            return (
              <div
                key={src.source}
                className="teyva-card hover-lift"
                style={{ padding: '14px 16px', display: 'flex', alignItems: 'center', gap: '11px' }}
              >
                <span className="teyva-icon-chip" style={{ background: chip.bg, color: chip.fg }}>
                  {SOURCE_ICONS[src.source] ?? <Building2 size={17} />}
                </span>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontWeight: 700, fontSize: '13px', color: 'var(--foreground)' }}>
                    {SOURCE_LABELS[src.source] ?? src.source}
                  </div>
                  <span className={statusBadgeClass(src.status)} style={{ fontSize: '10.5px', padding: '2px 8px', marginTop: '4px' }}>
                    <span className="dot" /> {statusLabel(src.status)}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Tabla de fuentes (patrón Staff List) */}
      {health && (
        <div className="teyva-card anim-fade-up" style={{ padding: '8px 18px 14px', overflowX: 'auto' }}>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Fuente</TableHead>
                <TableHead>Último éxito</TableHead>
                <TableHead>Retraso</TableHead>
                <TableHead>Éxito 24 h</TableHead>
                <TableHead>Estado</TableHead>
                <TableHead className="text-right">Historial</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {health.sources.map((src: ScraperSourceHealth) => {
                const chip = SOURCE_CHIP[src.source] ?? { bg: 'var(--muted)', fg: 'var(--muted-foreground)' };
                const runs = timeline?.sources[src.source] ?? [];
                const isOpen = expanded === src.source;
                return (
                  <Fragment key={src.source}>
                    <TableRow style={{ cursor: 'pointer' }} onClick={() => setExpanded(isOpen ? null : src.source)}>
                      <TableCell>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '11px' }}>
                          <span className="teyva-icon-chip" style={{ background: chip.bg, color: chip.fg }}>
                            {SOURCE_ICONS[src.source] ?? <Building2 size={17} />}
                          </span>
                          <div>
                            <div style={{ fontWeight: 700, fontSize: '13.5px', color: 'var(--foreground)' }}>
                              {SOURCE_LABELS[src.source] ?? src.source}
                            </div>
                            <div style={{ fontSize: '11.5px', color: 'var(--muted-foreground)' }}>
                              {SOURCE_DESCS[src.source] ?? ''}
                            </div>
                          </div>
                        </div>
                      </TableCell>
                      <TableCell style={{ color: lagColor(src.data_lag_minutes, src.interval_minutes), fontWeight: 600, fontSize: '13px' }}>
                        {relativeTime(src.last_success_at)}
                      </TableCell>
                      <TableCell style={{ color: lagColor(src.data_lag_minutes, src.interval_minutes), fontSize: '13px' }}>
                        {src.data_lag_minutes !== null ? `${src.data_lag_minutes} min` : '—'}
                      </TableCell>
                      <TableCell style={{ fontSize: '13px' }}>
                        {src.success_rate_24h !== null ? `${src.success_rate_24h}%` : '—'}
                        <span style={{ color: 'var(--muted-foreground)', marginLeft: '6px', fontSize: '11.5px' }}>
                          ({src.total_runs_24h} corridas)
                        </span>
                      </TableCell>
                      <TableCell>
                        <span className={statusBadgeClass(src.status)}>
                          <span className="dot" /> {statusLabel(src.status)}
                        </span>
                        {src.consecutive_failures > 0 && (
                          <span style={{ marginLeft: '8px', fontSize: '11.5px', color: 'var(--badge-danger-fg)', fontWeight: 600 }}>
                            {src.consecutive_failures} fallo{src.consecutive_failures > 1 ? 's' : ''}
                          </span>
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        <ChevronDown
                          size={16}
                          style={{
                            display: 'inline-block',
                            color: 'var(--muted-foreground)',
                            transform: isOpen ? 'rotate(180deg)' : 'none',
                            transition: 'transform 0.2s',
                          }}
                        />
                      </TableCell>
                    </TableRow>
                    {isOpen && (
                      <TableRow>
                        <TableCell colSpan={6} style={{ background: 'var(--muted)', padding: '14px 18px' }}>
                          {src.last_detail && (
                            <p style={{ fontSize: '12.5px', color: 'var(--muted-foreground)', margin: '0 0 10px' }}>
                              Último detalle: {src.last_detail}
                            </p>
                          )}
                          <RunTimeline runs={runs} />
                        </TableCell>
                      </TableRow>
                    )}
                  </Fragment>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}

      {error && (
        <p style={{ fontSize: '12px', color: 'var(--badge-danger-fg)', textAlign: 'center' }}>
          Último intento falló: {error}
        </p>
      )}
    </div>
  );
}
