'use client';

import { useState } from 'react';
import { MapPinned, Loader2 } from 'lucide-react';
import { fetchEvacuationRoutes, type EvacuationZone } from '@/lib/api';

interface EvacuationRoutesCardProps {
  communeId: string;
}

export function EvacuationRoutesCard({ communeId }: EvacuationRoutesCardProps) {
  const [zones, setZones] = useState<EvacuationZone[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchEvacuationRoutes(communeId);
      if (result.error) {
        setError(result.error);
        setZones([]);
      } else {
        setZones(result.zones);
      }
    } catch {
      setError('No se pudieron cargar las rutas de evacuación.');
      setZones([]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="teyva-card anim-fade-up" style={{ padding: '20px 22px' }}>
      <div className="flex items-center justify-between gap-3 flex-wrap" style={{ marginBottom: zones ? '14px' : 0 }}>
        <div style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: 'var(--muted-foreground)', display: 'flex', alignItems: 'center', gap: '7px' }}>
          <MapPinned size={13} />
          Rutas Seguras (MVP, sin validar)
        </div>
        {zones === null && (
          <button
            onClick={load}
            disabled={loading}
            className="press-scale"
            style={{
              padding: '7px 14px',
              borderRadius: '10px',
              border: 'none',
              cursor: loading ? 'default' : 'pointer',
              fontSize: '12.5px',
              fontWeight: 700,
              background: 'var(--primary)',
              color: 'var(--primary-foreground)',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              opacity: loading ? 0.6 : 1,
            }}
          >
            {loading && <Loader2 size={13} className="animate-spin" />}
            {loading ? 'Buscando…' : 'Buscar zonas seguras'}
          </button>
        )}
      </div>

      {error && (
        <p style={{ fontSize: '12.5px', color: 'var(--muted-foreground)', margin: 0 }}>{error}</p>
      )}

      {zones && zones.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '9px' }}>
          {zones.map((z) => (
            <div
              key={z.id}
              style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '10px', padding: '10px 12px', borderRadius: '11px', background: 'var(--muted)' }}
            >
              <div style={{ minWidth: 0 }}>
                <div className="truncate" style={{ fontSize: '12.5px', fontWeight: 700, color: 'var(--foreground)' }}>
                  {z.nombre}
                </div>
                <div style={{ fontSize: '11.5px', color: 'var(--muted-foreground)', marginTop: '1px', textTransform: 'capitalize' }}>
                  {z.tipo === 'park' ? 'Parque' : z.tipo === 'school' ? 'Colegio' : 'Estadio'}
                </div>
              </div>
              <div style={{ fontSize: '12.5px', fontWeight: 700, color: 'var(--foreground)', whiteSpace: 'nowrap' }}>
                {z.duration_walking_min != null ? `${z.duration_walking_min.toFixed(0)} min` : `${z.distance_straight_km} km`}
              </div>
            </div>
          ))}
          <p style={{ fontSize: '11px', color: 'var(--muted-foreground)', margin: '3px 0 0', lineHeight: 1.4 }}>
            Candidatos de OpenStreetMap, sin validar por Defensoría Civil o DAGRD. En emergencia real, llama primero al DAGRD 4444444.
          </p>
        </div>
      )}
    </div>
  );
}
