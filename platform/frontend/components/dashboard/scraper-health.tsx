'use client';

import { useEffect, useState } from 'react';
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

const SOURCE_ICONS: Record<string, string> = {
  siata: '🌧',
  dagrd: '⛰',
  ideam: '🌡',
  medellin_datos: '🏙',
};

function statusColor(s: string): string {
  if (s === 'healthy') return 'oklch(0.52 0.16 145)';
  if (s === 'warning') return 'oklch(0.65 0.17 65)';
  if (s === 'critical') return 'oklch(0.58 0.22 28)';
  return 'oklch(0.55 0.05 60)';
}

function statusBg(s: string): string {
  if (s === 'healthy') return 'oklch(0.95 0.04 145)';
  if (s === 'warning') return 'oklch(0.97 0.05 75)';
  if (s === 'critical') return 'oklch(0.97 0.04 22)';
  return 'oklch(0.94 0.01 60)';
}

function statusLabel(s: string): string {
  if (s === 'healthy') return 'Activo';
  if (s === 'warning') return 'Alerta';
  if (s === 'critical') return 'Caído';
  return 'Sin datos';
}

function statusIcon(s: string): string {
  if (s === 'healthy') return '✅';
  if (s === 'warning') return '⚠️';
  if (s === 'critical') return '❌';
  return '❓';
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
  if (lag === null) return 'oklch(0.55 0.05 60)';
  if (lag <= interval * 1.5) return 'oklch(0.52 0.16 145)';
  if (lag <= interval * 3) return 'oklch(0.65 0.17 65)';
  return 'oklch(0.58 0.22 28)';
}

function runDotColor(status: string): string {
  if (status === 'ok' || status === 'completed' || status === 'success') return 'oklch(0.52 0.16 145)';
  if (status === 'started') return 'oklch(0.65 0.17 65)';
  return 'oklch(0.58 0.22 28)';
}

// ── sub-components ─────────────────────────────────────────────────────────────

function RunTimeline({ runs }: { runs: ScraperRunEntry[] }) {
  if (!runs.length) return <p style={{ fontSize: '12px', color: 'oklch(0.6 0.03 55)', fontStyle: 'italic' }}>Sin registros aún</p>;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '5px', marginTop: '10px' }}>
      {runs.map((r) => (
        <div
          key={r.id}
          style={{
            display: 'grid',
            gridTemplateColumns: '10px 1fr auto',
            alignItems: 'center',
            gap: '8px',
            padding: '6px 10px',
            borderRadius: '8px',
            background: 'oklch(0.97 0.01 75)',
            fontSize: '12px',
          }}
        >
          <span
            style={{
              width: '8px', height: '8px', borderRadius: '99px',
              background: runDotColor(r.status), flexShrink: 0,
            }}
          />
          <span style={{ color: 'oklch(0.35 0.04 50)' }}>
            {r.run_started_at
              ? new Date(r.run_started_at).toLocaleString('es-CO', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
              : '—'}
            {r.records_valid != null && (
              <span style={{ marginLeft: '8px', color: 'oklch(0.55 0.04 55)' }}>
                {r.records_valid} válidos
              </span>
            )}
          </span>
          <span
            style={{
              fontSize: '11px', fontWeight: 600, padding: '2px 7px', borderRadius: '99px',
              background: statusBg(r.status === 'ok' || r.status === 'completed' || r.status === 'success' ? 'healthy' : r.status === 'started' ? 'warning' : 'critical'),
              color: statusColor(r.status === 'ok' || r.status === 'completed' || r.status === 'success' ? 'healthy' : r.status === 'started' ? 'warning' : 'critical'),
            }}
          >
            {r.status}
          </span>
        </div>
      ))}
    </div>
  );
}

function SourceCard({
  src,
  runs,
}: {
  src: ScraperSourceHealth;
  runs: ScraperRunEntry[];
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      style={{
        borderRadius: '18px',
        border: `1.5px solid ${src.status === 'critical' ? 'oklch(0.88 0.06 22)' : src.status === 'warning' ? 'oklch(0.88 0.06 75)' : 'oklch(0.91 0.018 70)'}`,
        background: 'oklch(0.995 0.005 75)',
        padding: '18px 20px',
        display: 'flex',
        flexDirection: 'column',
        gap: '12px',
        transition: 'box-shadow 0.15s',
      }}
    >
      {/* Header row */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{ fontSize: '22px', lineHeight: 1 }}>{SOURCE_ICONS[src.source] ?? '📡'}</span>
          <div>
            <div style={{ fontWeight: 700, fontSize: '15px', color: 'oklch(0.28 0.04 45)', lineHeight: 1.2 }}>
              {SOURCE_LABELS[src.source] ?? src.source}
            </div>
            <div style={{ fontSize: '11.5px', color: 'oklch(0.55 0.035 55)', marginTop: '2px' }}>
              {SOURCE_DESCS[src.source] ?? ''}
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
          <span
            style={{
              display: 'inline-flex', alignItems: 'center', gap: '5px',
              padding: '5px 11px', borderRadius: '99px',
              background: statusBg(src.status), color: statusColor(src.status),
              fontSize: '12.5px', fontWeight: 700,
            }}
          >
            {statusIcon(src.status)} {statusLabel(src.status)}
          </span>
        </div>
      </div>

      {/* Stats grid */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '10px' }}>
        <Stat
          label="Último éxito"
          value={relativeTime(src.last_success_at)}
          color={lagColor(src.data_lag_minutes, src.interval_minutes)}
        />
        <Stat
          label="Retraso actual"
          value={src.data_lag_minutes !== null ? `${src.data_lag_minutes} min` : '—'}
          color={lagColor(src.data_lag_minutes, src.interval_minutes)}
        />
        <Stat
          label="Éxito 24 h"
          value={src.success_rate_24h !== null ? `${src.success_rate_24h}%` : '—'}
          color={
            src.success_rate_24h === null ? 'oklch(0.55 0.04 55)'
              : src.success_rate_24h >= 80 ? 'oklch(0.52 0.16 145)'
              : src.success_rate_24h >= 50 ? 'oklch(0.65 0.17 65)'
              : 'oklch(0.58 0.22 28)'
          }
        />
      </div>

      {src.consecutive_failures > 0 && (
        <div
          style={{
            display: 'flex', alignItems: 'center', gap: '8px',
            padding: '8px 12px', borderRadius: '10px',
            background: src.consecutive_failures >= 3 ? 'oklch(0.97 0.04 22)' : 'oklch(0.97 0.05 75)',
            fontSize: '12.5px', color: src.consecutive_failures >= 3 ? 'oklch(0.45 0.18 28)' : 'oklch(0.45 0.14 65)',
            fontWeight: 600,
          }}
        >
          {src.consecutive_failures >= 3 ? '❌' : '⚠️'}
          {src.consecutive_failures} fallo{src.consecutive_failures > 1 ? 's' : ''} consecutivo{src.consecutive_failures > 1 ? 's' : ''}
          {src.last_detail && (
            <span style={{ fontWeight: 400, color: 'oklch(0.5 0.06 50)', marginLeft: '6px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '220px' }}>
              — {src.last_detail}
            </span>
          )}
        </div>
      )}

      {/* Expand / collapse timeline */}
      <button
        onClick={() => setExpanded((v) => !v)}
        style={{
          alignSelf: 'flex-start', background: 'none', border: 'none', cursor: 'pointer',
          fontSize: '12px', color: 'oklch(0.5 0.04 55)', padding: 0, display: 'flex', alignItems: 'center', gap: '4px',
        }}
      >
        {expanded ? '▲' : '▼'} {expanded ? 'Ocultar historial' : `Ver últimas ${runs.length} corridas`}
      </button>

      {expanded && <RunTimeline runs={runs} />}
    </div>
  );
}

function Stat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div
      style={{
        borderRadius: '11px', padding: '10px 12px',
        background: 'oklch(0.96 0.012 75)',
        display: 'flex', flexDirection: 'column', gap: '4px',
      }}
    >
      <div style={{ fontSize: '10.5px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'oklch(0.6 0.03 55)' }}>
        {label}
      </div>
      <div style={{ fontSize: '15px', fontWeight: 700, color: color ?? 'oklch(0.28 0.04 45)' }}>
        {value}
      </div>
    </div>
  );
}

function OverallBadge({ overall }: { overall: 'healthy' | 'warning' | 'critical' }) {
  const label = overall === 'healthy' ? 'Todo en orden' : overall === 'warning' ? 'Requiere atención' : 'Intervención necesaria';
  const icon = overall === 'healthy' ? '✅' : overall === 'warning' ? '⚠️' : '🚨';
  return (
    <div
      style={{
        display: 'inline-flex', alignItems: 'center', gap: '8px',
        padding: '9px 16px', borderRadius: '99px',
        background: statusBg(overall), color: statusColor(overall),
        fontSize: '14px', fontWeight: 700,
      }}
    >
      {icon} {label}
    </div>
  );
}

// ── main component ─────────────────────────────────────────────────────────────

export function ScraperHealth() {
  const [health, setHealth] = useState<ScraperHealthResponse | null>(null);
  const [timeline, setTimeline] = useState<ScraperTimelineResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);

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
      <div style={{ textAlign: 'center', padding: '60px 0', color: 'oklch(0.55 0.03 55)' }}>
        Cargando estado del sistema…
      </div>
    );
  }

  if (error && !health) {
    return (
      <div style={{ textAlign: 'center', padding: '60px 0', color: 'oklch(0.58 0.22 28)' }}>
        {error}
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '22px' }}>
      {/* Title + overall badge */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <h2 style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '26px', color: 'oklch(0.26 0.04 45)', margin: 0, lineHeight: 1.1 }}>
            Salud del Sistema
          </h2>
          <p style={{ margin: '4px 0 0', fontSize: '13.5px', color: 'oklch(0.55 0.035 55)' }}>
            Estado de los scrapers de datos en tiempo real
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {health && <OverallBadge overall={health.overall} />}
          <button
            onClick={() => { setLoading(true); void load(); }}
            style={{
              padding: '8px 14px', borderRadius: '10px',
              border: '1px solid oklch(0.89 0.018 70)',
              background: 'oklch(0.99 0.008 75)',
              fontSize: '13px', color: 'oklch(0.4 0.04 50)',
              cursor: 'pointer', fontWeight: 500,
            }}
          >
            ↻ Actualizar
          </button>
        </div>
      </div>

      {lastRefresh && (
        <p style={{ margin: '-10px 0 0', fontSize: '12px', color: 'oklch(0.6 0.025 55)' }}>
          Actualizado {lastRefresh.toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit', second: '2-digit' })} · se refresca cada 60 s
        </p>
      )}

      {/* Summary row */}
      {health && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px' }}>
          {health.sources.map((src) => (
            <div
              key={src.source}
              style={{
                borderRadius: '14px',
                padding: '14px 16px',
                background: statusBg(src.status),
                border: `1px solid ${statusColor(src.status)}22`,
                display: 'flex', alignItems: 'center', gap: '10px',
              }}
            >
              <span style={{ fontSize: '20px' }}>{statusIcon(src.status)}</span>
              <div>
                <div style={{ fontWeight: 700, fontSize: '13px', color: 'oklch(0.28 0.04 45)' }}>
                  {SOURCE_LABELS[src.source] ?? src.source}
                </div>
                <div style={{ fontSize: '11.5px', color: statusColor(src.status), fontWeight: 600, marginTop: '2px' }}>
                  {statusLabel(src.status)}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Source cards */}
      {health && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          {health.sources.map((src) => (
            <SourceCard
              key={src.source}
              src={src}
              runs={timeline?.sources[src.source] ?? []}
            />
          ))}
        </div>
      )}

      {error && (
        <p style={{ fontSize: '12px', color: 'oklch(0.58 0.22 28)', textAlign: 'center' }}>
          Último intento falló: {error}
        </p>
      )}
    </div>
  );
}
