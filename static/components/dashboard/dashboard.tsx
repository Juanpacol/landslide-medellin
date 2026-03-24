'use client';

import { useState } from 'react';
import { AlertBanner } from './alert-banner';
import { MedellinMap } from './medellin-map';
import { CommuneInfo } from './commune-info';
import { RainfallChart } from './rainfall-chart';
import type { CommuneFeature } from '@/lib/api';
import { Mountain, BarChart3, MapPin } from 'lucide-react';

type CommuneProps = CommuneFeature['properties'];

export function Dashboard() {
  const [selectedCommune, setSelectedCommune] = useState<CommuneProps | null>(null);

  return (
    <div className="min-h-screen bg-[#0f172a] flex flex-col">
      {/* Header */}
      <header className="bg-[#1e293b] border-b border-[#334155] px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-[#3b82f6]/20 rounded-lg">
              <Mountain className="h-6 w-6 text-[#3b82f6]" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-[#f1f5f9]">
                Sistema de Análisis de Riesgo de Deslizamientos
              </h1>
              <p className="text-sm text-[#94a3b8]">
                Medellín, Colombia — Monitoreo en Tiempo Real
              </p>
            </div>
          </div>
          <div className="flex items-center gap-4 text-sm text-[#94a3b8]">
            <div className="flex items-center gap-2">
              <MapPin className="h-4 w-4" />
              <span>21 Comunas</span>
            </div>
            <div className="h-4 w-px bg-[#475569]" />
            <div className="flex items-center gap-2">
              <BarChart3 className="h-4 w-4" />
              <span>Datos reales — Supabase</span>
            </div>
          </div>
        </div>
      </header>

      {/* Alert Banner */}
      <AlertBanner />

      {/* Main Content */}
      <main className="flex-1 p-6">
        <div className="flex gap-6 h-full" style={{ minHeight: 'calc(100vh - 200px)' }}>
          {/* Left Panel - Map (60%) */}
          <div className="w-[60%] flex flex-col gap-4">
            <div className="bg-[#1e293b] rounded-lg p-4 border border-[#334155]">
              <h2 className="text-lg font-semibold text-[#f1f5f9] mb-1">
                Mapa de Riesgo — Zonas Críticas
              </h2>
              <p className="text-sm text-[#94a3b8]">
                Popular (C1) · Santa Cruz (C2) · Villa Hermosa (C8) — Haga clic para ver detalles
              </p>
            </div>
            <div className="flex-1 bg-[#1e293b] rounded-lg border border-[#334155] overflow-hidden">
              <MedellinMap
                onCommuneSelect={setSelectedCommune}
                selectedCommuneId={selectedCommune?.commune_id ?? null}
              />
            </div>
          </div>

          {/* Right Panel (40%) */}
          <div className="w-[40%] flex flex-col gap-6">
            <div>
              <h2 className="text-lg font-semibold text-[#f1f5f9] mb-3">
                Información de Comuna
              </h2>
              <CommuneInfo commune={selectedCommune} />
            </div>

            <div className="flex-1">
              <h2 className="text-lg font-semibold text-[#f1f5f9] mb-3">
                Análisis Temporal (30 días)
              </h2>
              <RainfallChart communeId={selectedCommune?.commune_id ?? null} />
            </div>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="bg-[#1e293b] border-t border-[#334155] px-6 py-3">
        <div className="flex items-center justify-between text-sm text-[#94a3b8]">
          <span>Fuentes: DAGRD · IDEAM · Alcaldía de Medellín</span>
          <span>DAGRD — Departamento Administrativo de Gestión del Riesgo de Desastres</span>
        </div>
      </footer>
    </div>
  );
}
