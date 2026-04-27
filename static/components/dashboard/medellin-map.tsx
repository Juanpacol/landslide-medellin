'use client';

import { useEffect, useRef, useState } from 'react';
import type { Map as LeafletMap } from 'leaflet';
import { fetchGeoJSON, type CommuneFeature } from '@/lib/api';
import barriosGeo from '@/lib/barrios-medellin.json';
import { useTheme } from 'next-themes';
import { Filter } from 'lucide-react';

const riskColors: Record<string, string> = {
  'Bajo': '#22c55e',
  'Medio': '#eab308',
  'Alto': '#f97316',
  'Crítico': '#ef4444',
};

function riskFromScore(score: number): CommuneFeature['properties']['categoria_riesgo'] {
  if (score >= 0.82) return 'Crítico';
  if (score >= 0.65) return 'Alto';
  if (score >= 0.4) return 'Medio';
  return 'Bajo';
}

interface MedellinMapProps {
  onCommuneSelect: (commune: CommuneFeature['properties']) => void;
  selectedCommuneId: string | null;
}

type BarrioProps = {
  codigo: string;
  nombre: string;
  comuna: string;
  municipio?: string;
};

type BarrioFeature = GeoJSON.Feature<GeoJSON.Geometry, BarrioProps>;
type BarriosCollection = GeoJSON.FeatureCollection<GeoJSON.Geometry, BarrioProps>;

export function MedellinMap({ onCommuneSelect, selectedCommuneId }: MedellinMapProps) {
  const mapContainer = useRef<HTMLDivElement>(null);
  const mapRef = useRef<LeafletMap | null>(null);
  const mapInitializingRef = useRef(false);
  const [isClient, setIsClient] = useState(false);
  const [filters, setFilters] = useState<Set<string>>(new Set(['Bajo', 'Medio', 'Alto', 'Crítico']));
  const [hillsideOnly, setHillsideOnly] = useState(false);
  const [visibleCount, setVisibleCount] = useState(0);
  const { resolvedTheme } = useTheme();

  useEffect(() => {
    setIsClient(true);
  }, []);

  useEffect(() => {
    if (!isClient || !mapContainer.current || mapRef.current || mapInitializingRef.current) return;

    const initMap = async () => {
      mapInitializingRef.current = true;
      try {
        const L = (await import('leaflet')).default;
        await import('leaflet/dist/leaflet.css');

        // En React Strict Mode (dev), el effect puede ejecutarse dos veces
        // antes de que mapRef se asigne. Limpiamos cualquier instancia previa.
        const existingLeafletId = (mapContainer.current as (HTMLDivElement & { _leaflet_id?: number }) | null)?._leaflet_id;
        if (existingLeafletId && mapContainer.current) {
          mapContainer.current.innerHTML = '';
        }

        const map = L.map(mapContainer.current!, {
        center: [6.255, -75.57],
        zoom: 10,
          zoomControl: true,
        });
        mapRef.current = map;

      const tileUrl =
        resolvedTheme === 'dark'
          ? 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png'
          : 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png';

      L.tileLayer(tileUrl, {
        attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
        subdomains: 'abcd',
        maxZoom: 19,
      }).addTo(map);

      // Cargar riesgo por comuna desde API y geometría por barrio desde JSON.
      // Si barrios falla, usar fallback por comuna para no romper el mapa.
      try {
        const comunaGeo = await fetchGeoJSON();
        const comunaById = new Map(
          comunaGeo.features.map((f) => [String(f.properties.commune_id), f.properties] as const)
        );

        const barrios = barriosGeo as BarriosCollection;
        const cleaned = {
          ...barrios,
          features: (barrios.features ?? []).filter((f) => !!f.geometry && !!f.properties?.codigo),
        } as BarriosCollection;

        const buildBarrioView = (feature: BarrioFeature) => {
          const p = feature.properties;
          const comunaIdRaw = parseInt(p.comuna, 10);
          const comunaId = Number.isFinite(comunaIdRaw) ? String(comunaIdRaw) : '';
          const comuna = comunaId ? comunaById.get(comunaId) : undefined;
          const baseScore = Number(comuna?.indice_riesgo ?? 0);
          const indice = Number.isFinite(baseScore) ? baseScore : 0;
          const categoria = comuna?.categoria_riesgo ?? riskFromScore(indice);
          const eventos = Number(comuna?.n_eventos ?? 0);

          return {
            commune_id: p.codigo,
            nombre_comuna: p.nombre,
            categoria_riesgo: categoria,
            indice_riesgo: Number(indice.toFixed(2)),
            n_eventos: eventos,
            is_zona_ladera: comuna?.is_zona_ladera ?? false,
            comuna_nombre: comuna?.nombre_comuna ?? `Comuna ${p.comuna}`,
            municipio: p.municipio ?? 'Medellin',
            parent_commune_id: comunaId || undefined,
            rain7d: undefined,
            rain30d: undefined,
            trend: 0,
          } as CommuneFeature['properties'] & { comuna_nombre: string; municipio: string };
        };

        const layer = L.geoJSON(cleaned, {
          style: (feature) => {
            const view = feature ? buildBarrioView(feature as BarrioFeature) : null;
            const risk = view?.categoria_riesgo ?? 'Bajo';
            const color = riskColors[risk] ?? '#22c55e';
            const isSelected = view?.commune_id === selectedCommuneId;
            const isVisible = !!view && filters.has(risk) && (!hillsideOnly || !!view.is_zona_ladera);
            return {
              color: isVisible ? color : 'transparent',
              fillColor: isVisible ? color : 'transparent',
              fillOpacity: isVisible ? (isSelected ? 0.8 : 0.58) : 0,
              weight: isVisible ? (isSelected ? 2.6 : 0.8) : 0,
            };
          },
          onEachFeature: (feature, layer) => {
            const props = buildBarrioView(feature as BarrioFeature);
            const tooltip = `${props.nombre_comuna} · ${props.comuna_nombre}`;
            layer.bindTooltip(tooltip, {
              permanent: false,
              direction: 'top',
              className: 'commune-tooltip',
            });
            layer.on('click', () => onCommuneSelect(props));
            layer.on('mouseover', () => {
              (layer as L.Path).setStyle({ fillOpacity: 0.82, weight: 2.2 });
            });
            layer.on('mouseout', () => {
              const isSelected = props.commune_id === selectedCommuneId;
              (layer as L.Path).setStyle({
                fillOpacity: isSelected ? 0.8 : 0.5,
                weight: isSelected ? 2.6 : 0.8,
              });
            });
          },
        }).addTo(map);

        // Mantener framing estable del valle para que visualmente coincida con el mock.
        map.setView([6.255, -75.57], 10);
        const visible = cleaned.features.reduce((acc, f) => {
          const view = buildBarrioView(f as BarrioFeature);
          return acc + (filters.has(view.categoria_riesgo) && (!hillsideOnly || !!view.is_zona_ladera) ? 1 : 0);
        }, 0);
        setVisibleCount(visible);
      } catch (barriosError) {
        console.warn('Mapa por barrios no disponible; usando fallback por comuna.', barriosError);
        try {
          const comunaGeo = await fetchGeoJSON();
          const cleanedComunas = {
            ...comunaGeo,
            features: comunaGeo.features.filter((f) => !!f.geometry && !!f.properties?.commune_id),
          } as GeoJSON.FeatureCollection;

          const layer = L.geoJSON(cleanedComunas, {
            style: (feature) => {
              const props = feature?.properties as CommuneFeature['properties'] | undefined;
              const risk = props?.categoria_riesgo ?? 'Bajo';
              const color = riskColors[risk] ?? '#22c55e';
              const isSelected = props?.commune_id === selectedCommuneId;
              const isVisible = !!props && filters.has(risk) && (!hillsideOnly || !!props.is_zona_ladera);
              return {
                color: isVisible ? color : 'transparent',
                fillColor: isVisible ? color : 'transparent',
                fillOpacity: isVisible ? (isSelected ? 0.8 : 0.58) : 0,
                weight: isVisible ? (isSelected ? 2.6 : 1.2) : 0,
              };
            },
            onEachFeature: (feature, layer) => {
              const props = feature.properties as CommuneFeature['properties'];
              layer.bindTooltip(props.nombre_comuna, {
                permanent: false,
                direction: 'center',
                className: 'commune-tooltip',
              });
              layer.on('click', () => onCommuneSelect(props));
            },
          }).addTo(map);

          const bounds = layer.getBounds();
          if (bounds.isValid()) map.fitBounds(bounds, { padding: [16, 16] });
          const visible = cleanedComunas.features.reduce((acc, f) => {
            const p = f.properties as CommuneFeature['properties'] | undefined;
            if (!p) return acc;
            return acc + (filters.has(p.categoria_riesgo) && (!hillsideOnly || !!p.is_zona_ladera) ? 1 : 0);
          }, 0);
          setVisibleCount(visible);
        } catch (fallbackError) {
          console.warn('También falló el fallback por comuna.', fallbackError);
        }
      }

      } finally {
        mapInitializingRef.current = false;
      }
    };

    void initMap();

    return () => {
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
      }
      mapInitializingRef.current = false;
    };
  }, [isClient, onCommuneSelect, selectedCommuneId, resolvedTheme, filters, hillsideOnly]);

  if (!isClient) {
    return (
      <div className="w-full h-full bg-[#1e293b] rounded-lg flex items-center justify-center">
        <div className="text-[#94a3b8]">Cargando mapa...</div>
      </div>
    );
  }

  return (
    <div className="relative w-full h-full rounded-3xl overflow-hidden border border-border/60 bg-card shadow-[var(--shadow-soft)]">
      <div className="absolute left-3 right-3 top-3 z-[1000] flex flex-wrap items-center gap-2 rounded-xl border border-border/60 bg-card/95 px-3 py-2 backdrop-blur supports-[backdrop-filter]:bg-card/80">
        <div className="flex items-center gap-1 text-sm font-semibold text-foreground">
          <Filter className="h-4 w-4 text-muted-foreground" />
          Niveles
        </div>
        {(['Bajo', 'Medio', 'Alto', 'Crítico'] as const).map((label) => {
          const active = filters.has(label);
          return (
            <button
              key={label}
              onClick={() =>
                setFilters((prev) => {
                  const next = new Set(prev);
                  if (next.has(label)) next.delete(label);
                  else next.add(label);
                  return next;
                })
              }
              className={`rounded-full border px-2 py-0.5 text-xs font-semibold ${active ? 'bg-secondary text-foreground border-transparent' : 'text-muted-foreground border-border/60'}`}
            >
              <span className="mr-1 inline-block h-2 w-2 rounded-full" style={{ backgroundColor: riskColors[label] }} />
              {label}
            </button>
          );
        })}
        <button
          onClick={() => setHillsideOnly((v) => !v)}
          className={`ml-2 rounded-full border px-3 py-0.5 text-xs font-semibold ${hillsideOnly ? 'bg-secondary text-foreground border-transparent' : 'text-muted-foreground border-border/60'}`}
        >
          Solo zonas de ladera
        </button>
        <span className="ml-auto text-xs text-muted-foreground">{visibleCount} barrios visibles</span>
      </div>
      <div
        ref={mapContainer}
        className="w-full h-full rounded-3xl overflow-hidden"
        style={{ minHeight: '500px' }}
      />
      <div className="pointer-events-none absolute left-4 top-20 z-[1000] rounded-2xl border border-border/70 bg-card/95 px-4 py-3 shadow-[var(--shadow-soft)]">
        <div className="mb-2 text-sm font-semibold text-foreground">Nivel de riesgo</div>
        <div className="space-y-1.5">
          {Object.entries(riskColors).map(([label, color]) => (
            <div key={label} className="flex items-center gap-2 text-sm text-muted-foreground">
              <span className="inline-block h-3 w-3 rounded-full" style={{ backgroundColor: color }} />
              <span>{label}</span>
            </div>
          ))}
        </div>
        <div className="mt-2 border-t border-border/60 pt-2 text-xs text-muted-foreground">Granularidad: barrio</div>
      </div>
    </div>
  );
}
