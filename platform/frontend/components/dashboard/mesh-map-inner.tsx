'use client';

import { useEffect, useState } from 'react';
import { GeoJSON, MapContainer, TileLayer, Tooltip as LeafletTooltip } from 'react-leaflet';
import { fetchMeshGrid, type MeshQuadrantEntry } from '@/lib/api';

// Mismo esquema de color que barrios-map-inner.tsx::hazardColor(), reutilizado
// para consistencia visual entre capas del mapa.
function hazardColor(grade: string | null | undefined): string {
  const g = (grade ?? '').toLowerCase();
  if (g.includes('alta')) return 'oklch(0.62 0.22 25)';
  if (g.includes('media')) return 'oklch(0.72 0.12 70)';
  if (g.includes('baja')) return 'oklch(0.65 0.13 140)';
  return 'oklch(0.75 0.01 260)';
}

function hazardLabel(grade: string | null | undefined): string {
  return grade && grade.trim() ? grade : 'Sin dato oficial';
}

interface MeshMapInnerProps {
  onOpenProfile?: (communeId: string) => void;
}

export default function MeshMapInner({ onOpenProfile }: MeshMapInnerProps) {
  const [quadrants, setQuadrants] = useState<MeshQuadrantEntry[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    fetchMeshGrid()
      .then((d) => setQuadrants(d.quadrants))
      .catch(() => setQuadrants([]))
      .finally(() => setLoaded(true));
  }, []);

  return (
    <div className="relative h-full w-full overflow-hidden" style={{ borderRadius: '24px' }}>
      <MapContainer
        center={[6.26, -75.58]}
        zoom={12}
        style={{ height: '100%', width: '100%', background: 'var(--muted)' }}
        scrollWheelZoom
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
        />
        {loaded &&
          quadrants.map((q) => {
            const color = hazardColor(q.hazard_grade);
            return (
              <GeoJSON
                key={q.id}
                data={{ type: 'Feature', properties: {}, geometry: q.geometry } as GeoJSON.Feature}
                style={{ color, weight: 1, fillColor: color, fillOpacity: 0.3 }}
                eventHandlers={{
                  click: () => {
                    if (onOpenProfile && q.commune_ids[0]) onOpenProfile(q.commune_ids[0]);
                  },
                  mouseover: (e) => e.target.setStyle({ fillOpacity: 0.6, weight: 2 }),
                  mouseout: (e) => e.target.setStyle({ fillOpacity: 0.3, weight: 1 }),
                }}
              >
                <LeafletTooltip sticky>
                  <div style={{ fontFamily: 'var(--font-sans)', fontSize: '12px' }}>
                    <strong>{q.id}</strong>
                    <br />
                    Comuna(s): {q.commune_ids.join(', ') || '—'}
                    <br />
                    Amenaza: {hazardLabel(q.hazard_grade)} ({q.n_barrios_alta} barrios en Alta)
                  </div>
                </LeafletTooltip>
              </GeoJSON>
            );
          })}
      </MapContainer>

      <div
        className="absolute bottom-4 left-4 z-[1000]"
        style={{
          borderRadius: '14px',
          background: 'var(--glass-bg)',
          backdropFilter: 'blur(8px)',
          padding: '11px 14px',
          border: '1px solid var(--border)',
          display: 'flex',
          flexDirection: 'column',
          gap: '6px',
          maxWidth: '220px',
        }}
      >
        <div style={{ fontSize: '10.5px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--muted-foreground)' }}>
          Mesh Maps — cuadrículas ~1.5km
        </div>
        {[
          ['Alta', 'oklch(0.62 0.22 25)'],
          ['Media', 'oklch(0.72 0.12 70)'],
          ['Baja', 'oklch(0.65 0.13 140)'],
          ['Sin dato', 'oklch(0.75 0.01 260)'],
        ].map(([label, color]) => (
          <div key={label} style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '11.5px', fontWeight: 500, color: 'var(--foreground)' }}>
            <span style={{ height: '10px', width: '10px', borderRadius: '99px', background: color, flexShrink: 0 }} />
            {label}
          </div>
        ))}
        <div style={{ fontSize: '10px', color: 'var(--muted-foreground)', marginTop: '4px', lineHeight: 1.4 }}>
          Amenaza heredada de la comuna — no es predicción por cuadrícula.
        </div>
      </div>
    </div>
  );
}
