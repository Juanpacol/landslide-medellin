'use client';

import { useEffect, useState } from 'react';
import { AlertCircle } from 'lucide-react';

interface ModelFeaturesProps {
  communeId: string;
  riskScore: number | null;
  riskCategory: string;
}

export function ModelFeaturesPanel({ communeId, riskScore, riskCategory }: ModelFeaturesProps) {
  const [features, setFeatures] = useState<Record<string, number | string> | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // TODO: endpoint real GET /api/risk/predictions/latest/{commune_id}/debug
    // Por ahora mostramos features disponibles
    setLoading(false);
  }, [communeId]);

  const zoneType = (() => {
    if (['El Poblado', 'La Candelaria', 'Laureles-Estadio', 'La América'].includes(communeId)) return 'CÉNTRICA';
    if (['San Cristóbal', 'San Javier', 'Belén', 'Robledo', 'Palmitas'].includes(communeId)) return 'LADERA';
    return 'MIXTA';
  })();

  const hasInconsistency = zoneType === 'CÉNTRICA' && riskScore && riskScore > 0.65;

  return (
    <div style={{ fontSize: '12px', color: 'var(--foreground)', lineHeight: 1.6 }}>
      {/* Información de la comuna */}
      <div
        style={{
          marginBottom: '14px',
          padding: '10px 12px',
          borderRadius: '8px',
          background: 'var(--muted)',
          border: hasInconsistency ? '1px solid oklch(0.9 0.15 25)' : 'none',
        }}
      >
        <div style={{ fontWeight: 700, marginBottom: '4px' }}>Score: {riskScore?.toFixed(3) || '—'}</div>
        <div style={{ fontSize: '11px', color: 'var(--muted-foreground)' }}>
          Categoría: <strong>{riskCategory}</strong> | Zona: <strong>{zoneType}</strong>
        </div>
      </div>

      {/* Advertencia de inconsistencia */}
      {hasInconsistency && (
        <div
          style={{
            marginBottom: '12px',
            padding: '10px',
            borderRadius: '8px',
            background: 'oklch(0.95 0.08 25 / 0.3)',
            border: '1px solid oklch(0.9 0.15 25)',
            display: 'flex',
            gap: '8px',
            fontSize: '11px',
            color: 'oklch(0.4 0.15 25)',
          }}
        >
          <AlertCircle size={16} style={{ flexShrink: 0, marginTop: '2px' }} />
          <span>
            <strong>⚠️ Posible inconsistencia</strong>: zona céntrica con predicción alta. Modelo necesita calibración con datos históricos reales.
          </span>
        </div>
      )}

      {/* Features utilizadas */}
      <div style={{ marginBottom: '12px' }}>
        <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--muted-foreground)', marginBottom: '6px' }}>
          FEATURES DISPONIBLES:
        </div>
        <div style={{ fontSize: '11px', color: 'var(--muted-foreground)', lineHeight: 1.8 }}>
          • <strong>Precipitación</strong> (snapshot, SIATA)<br />
          • <strong>Ubicación</strong> (centroide lat/lon)<br />
          • <strong>Intensidad sísmica</strong> (últimos 30 días, red SIATA)<br />
          • <strong>Índice antecedente</strong> (precipitación acumulada 30 días)<br />
          • <strong>Amenaza por barrio</strong> (% de barrios en "Alta" per commune)<br />
          • <strong>SWI</strong> (saturación del suelo, modelo de tanque JMA)<br />
          • <strong>Conteo de estaciones</strong> (SIATA)
        </div>
      </div>

      {/* Limitaciones MVP */}
      <div
        style={{
          padding: '10px 12px',
          borderRadius: '8px',
          background: 'oklch(0.95 0.06 260 / 0.4)',
          border: '1px solid var(--border)',
          fontSize: '10px',
          color: 'var(--muted-foreground)',
          lineHeight: 1.6,
        }}
      >
        <div style={{ fontWeight: 700, marginBottom: '4px', color: 'var(--foreground)' }}>
          📋 MVP — Limitaciones Conocidas:
        </div>
        <ol style={{ paddingLeft: '16px', margin: 0 }}>
          <li>Entrenado con backfill histórico sin datos reales de deslizamientos con timestamp</li>
          <li>Sesgo geográfico: zonas céntricas predichas con riesgo más alto que lo justificable</li>
          <li>Parámetros de SWI y Snake Line conservadores, sin calibración con eventos</li>
          <li>Requiere: datos históricos de DAGRD/Defensoría con fecha/hora/ubicación precisa</li>
        </ol>
      </div>
    </div>
  );
}
