'use client';

import { MapPin, Droplets, Mountain, AlertCircle } from 'lucide-react';
import type { CommuneFeature } from '@/lib/api';

type CommuneProps = CommuneFeature['properties'];

const riskColors: Record<string, string> = {
  'Bajo': '#22c55e',
  'Medio': '#eab308',
  'Alto': '#f97316',
  'Crítico': '#ef4444',
};

interface CommuneInfoProps {
  commune: CommuneProps | null;
}

export function CommuneInfo({ commune }: CommuneInfoProps) {
  if (!commune) {
    return (
      <div className="bg-[#1e293b] rounded-lg p-6 border border-[#334155]">
        <div className="flex flex-col items-center justify-center py-8 text-[#94a3b8]">
          <MapPin className="h-12 w-12 mb-3 opacity-50" />
          <p className="text-center">
            Seleccione una comuna en el mapa para ver sus detalles
          </p>
        </div>
      </div>
    );
  }

  const riskColor = riskColors[commune.categoria_riesgo] ?? '#22c55e';

  return (
    <div className="bg-[#1e293b] rounded-lg p-6 border border-[#334155]">
      <div className="flex items-start justify-between mb-4">
        <div>
          <h3 className="text-xl font-bold text-[#f1f5f9]">{commune.nombre_comuna}</h3>
          <p className="text-[#94a3b8] text-sm">Comuna {commune.commune_id}</p>
        </div>
        <span
          className="px-3 py-1 rounded-full text-sm font-bold"
          style={{
            backgroundColor: `${riskColor}20`,
            color: riskColor,
            border: `1px solid ${riskColor}`,
          }}
        >
          {commune.categoria_riesgo}
        </span>
      </div>

      <div className="grid gap-4">
        <div className="flex items-center gap-3 bg-[#0f172a] rounded-lg p-4">
          <div className="p-2 bg-[#ef4444]/20 rounded-lg">
            <AlertCircle className="h-5 w-5 text-[#ef4444]" />
          </div>
          <div>
            <p className="text-[#94a3b8] text-xs uppercase tracking-wide">
              Eventos de Deslizamiento
            </p>
            <p className="text-[#f1f5f9] text-lg font-bold">{commune.n_eventos}</p>
          </div>
        </div>

        <div className="flex items-center gap-3 bg-[#0f172a] rounded-lg p-4">
          <div className="p-2 bg-[#3b82f6]/20 rounded-lg">
            <Droplets className="h-5 w-5 text-[#3b82f6]" />
          </div>
          <div>
            <p className="text-[#94a3b8] text-xs uppercase tracking-wide">
              Índice de Riesgo
            </p>
            <p className="text-[#f1f5f9] text-lg font-bold">
              {commune.indice_riesgo?.toFixed(2) ?? '—'}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3 bg-[#0f172a] rounded-lg p-4">
          <div className={`p-2 rounded-lg ${commune.is_zona_ladera ? 'bg-[#f59e0b]/20' : 'bg-[#22c55e]/20'}`}>
            <Mountain className={`h-5 w-5 ${commune.is_zona_ladera ? 'text-[#f59e0b]' : 'text-[#22c55e]'}`} />
          </div>
          <div>
            <p className="text-[#94a3b8] text-xs uppercase tracking-wide">Zona de Ladera</p>
            <p className={`text-lg font-bold ${commune.is_zona_ladera ? 'text-[#f59e0b]' : 'text-[#22c55e]'}`}>
              {commune.is_zona_ladera ? 'Sí' : 'No'}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
