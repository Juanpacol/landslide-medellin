'use client';

import { useEffect, useRef, useState } from 'react';
import type { Map as LeafletMap } from 'leaflet';
import { fetchGeoJSON, type CommuneFeature } from '@/lib/api';

const riskColors: Record<string, string> = {
  'Bajo': '#22c55e',
  'Medio': '#eab308',
  'Alto': '#f97316',
  'Crítico': '#ef4444',
};

interface MedellinMapProps {
  onCommuneSelect: (commune: CommuneFeature['properties']) => void;
  selectedCommuneId: number | null;
}

export function MedellinMap({ onCommuneSelect, selectedCommuneId }: MedellinMapProps) {
  const mapContainer = useRef<HTMLDivElement>(null);
  const mapRef = useRef<LeafletMap | null>(null);
  const [isClient, setIsClient] = useState(false);

  useEffect(() => { setIsClient(true); }, []);

  useEffect(() => {
    if (!isClient || !mapContainer.current || mapRef.current) return;

    const initMap = async () => {
      const L = (await import('leaflet')).default;
      await import('leaflet/dist/leaflet.css');

      const map = L.map(mapContainer.current!, {
        center: [6.255, -75.565],
        zoom: 12,
        zoomControl: true,
      });

      L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
        subdomains: 'abcd',
        maxZoom: 19,
      }).addTo(map);

      // Cargar GeoJSON desde la API
      try {
        const geojson = await fetchGeoJSON();

        L.geoJSON(geojson as GeoJSON.FeatureCollection, {
          style: (feature) => {
            const risk = feature?.properties?.categoria_riesgo ?? 'Bajo';
            const color = riskColors[risk] ?? '#22c55e';
            const isSelected = feature?.properties?.commune_id === selectedCommuneId;
            return {
              color,
              fillColor: color,
              fillOpacity: isSelected ? 0.8 : 0.5,
              weight: isSelected ? 3 : 2,
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
            layer.on('mouseover', () => {
              (layer as L.Path).setStyle({ fillOpacity: 0.8, weight: 3 });
            });
            layer.on('mouseout', () => {
              const isSelected = props.commune_id === selectedCommuneId;
              (layer as L.Path).setStyle({
                fillOpacity: isSelected ? 0.8 : 0.5,
                weight: isSelected ? 3 : 2,
              });
            });
          },
        }).addTo(map);
      } catch {
        console.error('No se pudo cargar el GeoJSON de la API');
      }

      // Leyenda
      const legend = L.control({ position: 'bottomright' });
      legend.onAdd = () => {
        const div = L.DomUtil.create('div', 'legend');
        div.style.cssText = 'background:#1e293b;padding:10px;border-radius:8px;border:1px solid #334155;';
        div.innerHTML = `
          <div style="font-weight:bold;color:#f1f5f9;margin-bottom:8px;">Nivel de Riesgo</div>
          ${Object.entries(riskColors).map(([label, color]) => `
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
              <span style="width:16px;height:16px;background:${color};border-radius:2px;display:inline-block;"></span>
              <span style="color:#94a3b8;font-size:12px;">${label}</span>
            </div>`).join('')}
        `;
        return div;
      };
      legend.addTo(map);

      mapRef.current = map;
    };

    initMap();

    return () => {
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
      }
    };
  }, [isClient, onCommuneSelect, selectedCommuneId]);

  if (!isClient) {
    return (
      <div className="w-full h-full bg-[#1e293b] rounded-lg flex items-center justify-center">
        <div className="text-[#94a3b8]">Cargando mapa...</div>
      </div>
    );
  }

  return (
    <div
      ref={mapContainer}
      className="w-full h-full rounded-lg overflow-hidden"
      style={{ minHeight: '500px' }}
    />
  );
}
