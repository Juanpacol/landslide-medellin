'use client';

import { useEffect, useMemo, useState } from 'react';
import { GeoJSON, MapContainer, TileLayer, Tooltip as LeafletTooltip } from 'react-leaflet';
import type { Feature } from 'geojson';
import barriosGeo from '@/lib/barrios-medellin.json';
import { fetchBarriosHazard, type BarrioHazardEntry } from '@/lib/api';

interface BarriosMapInnerProps {
  onOpenProfile?: (communeId: string) => void;
}

// Colores por grado de amenaza oficial (capa VM_05, ordenamiento territorial).
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

export default function BarriosMapInner({ onOpenProfile }: BarriosMapInnerProps) {
  const [hazard, setHazard] = useState<Record<string, BarrioHazardEntry>>({});
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    fetchBarriosHazard()
      .then((d) => setHazard(d.barrios))
      .catch(() => setHazard({}))
      .finally(() => setLoaded(true));
  }, []);

  const features = useMemo(
    () => (barriosGeo as { features: Feature[] }).features,
    [],
  );

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
          features.map((feat, i) => {
            const props = (feat.properties ?? {}) as { codigo?: string; nombre?: string; comuna?: string };
            const codigo = String(props.codigo ?? i);
            const entry = hazard[codigo];
            const color = hazardColor(entry?.hazard_grade);
            return (
              <GeoJSON
                key={codigo}
                data={feat}
                style={{
                  color,
                  weight: 1,
                  fillColor: color,
                  fillOpacity: 0.35,
                }}
                eventHandlers={{
                  click: () => {
                    if (onOpenProfile && props.comuna) onOpenProfile(String(props.comuna));
                  },
                  mouseover: (e) => e.target.setStyle({ fillOpacity: 0.65, weight: 2 }),
                  mouseout: (e) => e.target.setStyle({ fillOpacity: 0.35, weight: 1 }),
                }}
              >
                <LeafletTooltip sticky>
                  <div style={{ fontFamily: 'var(--font-sans)', fontSize: '12px' }}>
                    <strong>{props.nombre ?? codigo}</strong>
                    <br />
                    Comuna {props.comuna ?? '—'} · Amenaza: {hazardLabel(entry?.hazard_grade)}
                  </div>
                </LeafletTooltip>
              </GeoJSON>
            );
          })}
      </MapContainer>

      {/* Leyenda flotante */}
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
        }}
      >
        <div style={{ fontSize: '10.5px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--muted-foreground)' }}>
          Amenaza por barrio
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
      </div>
    </div>
  );
}
