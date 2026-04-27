import { useMemo, useRef, useState } from "react";
import {
  GeoJSON,
  MapContainer,
  TileLayer,
  ZoomControl,
} from "react-leaflet";
import type { Feature, FeatureCollection, Geometry } from "geojson";
import type { Layer, PathOptions } from "leaflet";
import type { Comuna, RiskLevel } from "@/lib/teyva-data";
import { RISK_COLORS } from "@/lib/teyva-data";
import barriosGeo from "@/lib/barrios-medellin.json";
import { BARRIO_BY_ID, barrioAsComuna, type BarrioProps } from "@/lib/barrios-data";
import { Filter } from "lucide-react";

const FC = barriosGeo as unknown as FeatureCollection<Geometry, BarrioProps>;
const ALL_LEVELS: RiskLevel[] = ["Bajo", "Medio", "Alto", "Crítico"];

interface Props {
  selectedId: number | null;
  onSelect: (c: Comuna) => void;
}

export function RiskMap({ selectedId, onSelect }: Props) {
  const [filters, setFilters] = useState<Set<RiskLevel>>(new Set(ALL_LEVELS));
  const [hillsideOnly, setHillsideOnly] = useState(false);
  const [selectedBarrio, setSelectedBarrio] = useState<string | null>(null);
  const geoRef = useRef<L.GeoJSON | null>(null);

  const visibleIds = useMemo(() => {
    const ids = new Set<string>();
    BARRIO_BY_ID.forEach((b) => {
      if (filters.has(b.riskLevel) && (!hillsideOnly || b.hillside)) {
        ids.add(b.id);
      }
    });
    return ids;
  }, [filters, hillsideOnly]);

  const toggle = (l: RiskLevel) => {
    setFilters((prev) => {
      const n = new Set(prev);
      if (n.has(l)) n.delete(l);
      else n.add(l);
      return n;
    });
  };

  const styleFor = (
    feature?: Feature<Geometry, BarrioProps>,
  ): PathOptions => {
    if (!feature) return {};
    const id = feature.properties?.codigo;
    const b = id ? BARRIO_BY_ID.get(id) : undefined;
    if (!b || !visibleIds.has(b.id)) {
      return {
        color: "transparent",
        fillColor: "transparent",
        weight: 0,
        fillOpacity: 0,
      };
    }
    const isSelected = b.id === selectedBarrio;
    const color = RISK_COLORS[b.riskLevel];
    return {
      color: isSelected ? "#1F6F50" : color,
      weight: isSelected ? 2.5 : 0.6,
      fillColor: color,
      fillOpacity: isSelected ? 0.75 : 0.55,
      opacity: 0.9,
    };
  };

  const onEachFeature = (
    feature: Feature<Geometry, BarrioProps>,
    layer: Layer,
  ) => {
    const id = feature.properties?.codigo;
    const b = id ? BARRIO_BY_ID.get(id) : undefined;
    if (!b) return;

    const tooltipHtml = `
      <div style="min-width:180px">
        <div style="font-weight:600">${b.name}</div>
        <div style="font-size:11px;opacity:.75">${b.municipio} · ${b.comunaName}</div>
        <div style="display:flex;align-items:center;gap:6px;font-size:11px;margin-top:4px">
          <span style="display:inline-block;width:8px;height:8px;border-radius:9999px;background:${RISK_COLORS[b.riskLevel]}"></span>
          Riesgo ${b.riskLevel} · ${(b.riskScore * 100).toFixed(0)}%
        </div>
        <div style="font-size:11px;opacity:.8;margin-top:2px">
          ${b.events} eventos · ${b.rain7d}mm en 7d
        </div>
      </div>`;
    layer.bindTooltip(tooltipHtml, { sticky: true, direction: "top" });
    layer.on({
      click: () => {
        setSelectedBarrio(b.id);
        onSelect(barrioAsComuna(b));
      },
      mouseover: (e) => {
        const path = e.target as L.Path;
        path.setStyle({ weight: 2.2, fillOpacity: 0.78 });
      },
      mouseout: (e) => {
        const path = e.target as L.Path;
        if (geoRef.current) {
          geoRef.current.resetStyle(path as unknown as L.Path);
        }
      },
    });
  };

  // selectedId viene de la comuna; lo usamos solo para forzar re-render
  void selectedId;

  return (
    <div className="relative flex h-full flex-col overflow-hidden rounded-3xl border border-border/60 bg-card shadow-[var(--shadow-soft)]">
      {/* Filtros */}
      <div className="flex flex-wrap items-center gap-2 border-b border-border/60 bg-card/80 px-5 py-3 backdrop-blur">
        <div className="flex items-center gap-2 text-sm font-medium text-foreground">
          <Filter className="h-4 w-4 text-muted-foreground" />
          Niveles
        </div>
        {ALL_LEVELS.map((l) => {
          const active = filters.has(l);
          return (
            <button
              key={l}
              onClick={() => toggle(l)}
              className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium transition-all ${
                active
                  ? "border-transparent bg-secondary text-foreground"
                  : "border-border/60 text-muted-foreground hover:bg-muted"
              }`}
            >
              <span
                className="inline-block h-2 w-2 rounded-full"
                style={{ backgroundColor: RISK_COLORS[l] }}
              />
              {l}
            </button>
          );
        })}
        <div className="ml-2 hidden h-5 w-px bg-border md:block" />
        <button
          onClick={() => setHillsideOnly((v) => !v)}
          className={`rounded-full border px-2.5 py-1 text-xs font-medium transition-all ${
            hillsideOnly
              ? "border-transparent bg-[var(--leaf)]/20 text-foreground"
              : "border-border/60 text-muted-foreground hover:bg-muted"
          }`}
        >
          Solo zonas de ladera
        </button>
        <span className="ml-auto text-xs text-muted-foreground">
          {visibleIds.size} barrios visibles
        </span>
      </div>

      {/* Mapa */}
      <div className="relative flex-1">
        <MapContainer
          center={[6.295, -75.57]}
          zoom={11}
          zoomControl={false}
          scrollWheelZoom
          className="h-full w-full"
        >
          <TileLayer
            attribution='&copy; OpenStreetMap'
            url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
          />
          <ZoomControl position="bottomright" />
          <GeoJSON
            key={`${selectedBarrio}-${visibleIds.size}`}
            ref={(r) => {
              geoRef.current = r;
            }}
            data={FC}
            style={styleFor as L.StyleFunction}
            onEachFeature={onEachFeature}
          />
        </MapContainer>

        {/* Leyenda */}
        <div className="pointer-events-none absolute left-4 top-4 z-[400] rounded-2xl border border-border/60 bg-card/95 p-3 text-xs shadow-[var(--shadow-soft)] backdrop-blur">
          <div className="mb-2 font-semibold text-foreground">Nivel de riesgo</div>
          <div className="space-y-1.5">
            {ALL_LEVELS.map((l) => (
              <div key={l} className="flex items-center gap-2">
                <span
                  className="inline-block h-3 w-3 rounded-sm"
                  style={{ backgroundColor: RISK_COLORS[l] }}
                />
                <span className="text-muted-foreground">{l}</span>
              </div>
            ))}
          </div>
          <div className="mt-2 border-t border-border/60 pt-2 text-[10px] text-muted-foreground">
            Granularidad: barrio
          </div>
        </div>
      </div>
    </div>
  );
}
