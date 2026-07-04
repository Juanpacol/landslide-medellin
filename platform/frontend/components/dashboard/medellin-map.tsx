'use client'

import { useEffect, useState } from 'react'
import { MEDELLIN_GEO } from '@/lib/medellin-geo'
import { fetchGeoJSON, type CommuneFeature } from '@/lib/api'

interface MedellinMapProps {
  onCommuneSelect: (commune: CommuneFeature['properties']) => void
  selectedCommuneId: string | null
}

const RISK_COLORS: Record<string, string> = {
  Crítico: 'oklch(0.62 0.22 25)',
  Alto:    'oklch(0.68 0.15 45)',
  Medio:   'oklch(0.72 0.12 70)',
  Bajo:    'oklch(0.65 0.13 140)',
}

const RISK_SOFT: Record<string, string> = {
  Crítico: 'oklch(0.92 0.04 25)',
  Alto:    'oklch(0.93 0.035 48)',
  Medio:   'oklch(0.94 0.028 70)',
  Bajo:    'oklch(0.93 0.035 140)',
}

const COMUNAS_NAMES: Record<string, string> = {
  '1': 'Popular',        '2': 'Santa Cruz',    '3': 'Manrique',
  '4': 'Aranjuez',       '5': 'Castilla',      '6': 'Doce de Oct.',
  '7': 'Robledo',        '8': 'Villa Hermosa', '9': 'Buenos Aires',
  '10': 'Candelaria',    '11': 'Laureles',     '12': 'La América',
  '13': 'San Javier',    '14': 'El Poblado',   '15': 'Guayabal',
  '16': 'Belén',
  '50': 'Palmitas',      '60': 'San Cristóbal','70': 'Altavista',
  '80': 'S.A. de Prado', '90': 'Santa Elena',
}

// Datos de riesgo estáticos usados cuando el modelo aún no ha generado predicciones.
const COMUNAS_RISK_STATIC: Record<string, CommuneFeature['properties']['categoria_riesgo']> = {
  '1':  'Crítico', '2':  'Alto',   '3':  'Alto',
  '4':  'Medio',   '5':  'Medio',  '6':  'Alto',
  '7':  'Medio',   '8':  'Crítico','9':  'Alto',
  '10': 'Bajo',    '11': 'Bajo',   '12': 'Bajo',
  '13': 'Alto',    '14': 'Bajo',   '15': 'Medio',
  '16': 'Medio',   '50': 'Bajo',   '60': 'Alto',
  '70': 'Medio',   '80': 'Bajo',   '90': 'Bajo',
}

const IS_LADERA: Record<string, boolean> = {
  '1': true,  '2': true,  '3': true,  '4': false, '5': false,
  '6': true,  '7': true,  '8': true,  '9': true,  '10': false,
  '11': false,'12': false,'13': true, '14': false,'15': false,
  '16': true, '50': true, '60': true, '70': true, '80': false, '90': true,
}

type GeoEntry = { points: string; cx: number; cy: number }
type GeoData = {
  viewBox: string
  rellenoTF: string
  COMUNAS: Record<string, GeoEntry>
  CORR?: string[]
}

export function MedellinMap({ onCommuneSelect, selectedCommuneId }: MedellinMapProps) {
  const [communes, setCommunes] = useState<Map<string, CommuneFeature['properties']>>(new Map())
  const [hoveredId, setHoveredId] = useState<string | null>(null)

  const geo = MEDELLIN_GEO as GeoData

  useEffect(() => {
    fetchGeoJSON()
      .then((data) => {
        const map = new Map(data.features.map((f) => [String(f.properties.commune_id), f.properties]))
        setCommunes(map)
      })
      .catch(console.error)
  }, [])

  const getRiskLevel = (id: string): CommuneFeature['properties']['categoria_riesgo'] => {
    const commune = communes.get(id)
    // Use API data only when there's a real ML prediction (indice_riesgo is not null)
    if (commune && (commune.indice_riesgo as number | null) !== null) {
      return commune.categoria_riesgo
    }
    return COMUNAS_RISK_STATIC[id] ?? 'Bajo'
  }

  const getFallbackCommune = (id: string): CommuneFeature['properties'] => ({
    commune_id: id,
    nombre_comuna: COMUNAS_NAMES[id] ?? `Comuna ${id}`,
    categoria_riesgo: COMUNAS_RISK_STATIC[id] ?? 'Bajo',
    indice_riesgo: 0,
    n_eventos: 0,
    is_zona_ladera: IS_LADERA[id] ?? false,
  })

  return (
    <div
      className="relative w-full rounded-3xl border overflow-hidden"
      style={{
        height: '600px',
        borderColor: 'oklch(0.90 0.018 70)',
        background: 'linear-gradient(160deg, oklch(0.93 0.022 120) 0%, oklch(0.95 0.018 90) 45%, oklch(0.94 0.025 65) 100%)',
        boxShadow: '0 1px 2px oklch(0.5 0.05 50 / 0.04), 0 14px 36px -20px oklch(0.5 0.06 45 / 0.34)',
      }}
    >
      <svg
        viewBox={geo.viewBox}
        preserveAspectRatio="xMidYMid meet"
        className="w-full h-full"
      >
        {/* CORREGIMIENTOS — fondo gris (contexto geográfico) */}
        <g transform="rotate(90,102.24388,94.217647)">
          {(geo.CORR ?? []).map((points, idx) => (
            <polygon
              key={`corr-${idx}`}
              points={points}
              fill="oklch(0.92 0.012 75)"
              stroke="oklch(0.84 0.018 70)"
              strokeWidth="0.35"
              strokeLinejoin="round"
            />
          ))}
        </g>

        {/* COMUNAS — relleno coloreado por nivel de riesgo */}
        <g transform="rotate(90,102.24388,94.217647)">
          {Object.entries(geo.COMUNAS).map(([id, data]) => {
            const risk = getRiskLevel(id)
            const isSelected = selectedCommuneId === id
            const isHovered = hoveredId === id
            const fill = isSelected ? RISK_COLORS[risk] : RISK_SOFT[risk]
            const stroke = RISK_COLORS[risk]
            const strokeWidth = isSelected ? 2.5 : isHovered ? 1.8 : 1
            const fillOpacity = isSelected ? 0.92 : isHovered ? 0.78 : 1

            return (
              <polygon
                key={`commune-${id}`}
                points={data.points}
                fill={fill}
                fillOpacity={fillOpacity}
                stroke={stroke}
                strokeWidth={strokeWidth}
                strokeLinejoin="round"
                style={{ cursor: 'pointer', transition: 'all 0.15s ease' }}
                onClick={() => {
                  const commune = communes.get(id) ?? getFallbackCommune(id)
                  onCommuneSelect(commune)
                }}
                onMouseEnter={() => setHoveredId(id)}
                onMouseLeave={() => setHoveredId(null)}
              />
            )
          })}
        </g>

        {/* NÚMEROS de comunas (centrados, texto blanco) */}
        {Object.entries(geo.COMUNAS).map(([id, data]) => (
          <text
            key={`num-${id}`}
            x={data.cx}
            y={data.cy}
            textAnchor="middle"
            dominantBaseline="middle"
            fontSize="8"
            fontWeight="700"
            fill="oklch(1 0 0)"
            style={{ pointerEvents: 'none', textShadow: '0 0.5px 1.5px oklch(0.2 0.05 40 / 0.6)' }}
          >
            {id}
          </text>
        ))}

        {/* NOMBRES de comunas */}
        {Object.entries(geo.COMUNAS).map(([id, data]) => {
          const isSelected = selectedCommuneId === id
          return (
            <text
              key={`name-${id}`}
              x={data.cx}
              y={data.cy + 10}
              textAnchor="middle"
              fontSize="5"
              fontWeight="700"
              fill={isSelected ? 'oklch(0.99 0.01 80)' : 'oklch(0.24 0.04 45)'}
              style={{ pointerEvents: 'none', textShadow: '0 0 3px oklch(0.97 0.01 75)' }}
            >
              {COMUNAS_NAMES[id] ?? `C${id}`}
            </text>
          )
        })}
      </svg>

      {/* HEADER flotante */}
      <div className="absolute top-4 left-4 right-4 z-10 flex justify-between gap-4 pointer-events-none">
        <div
          style={{
            borderRadius: '14px',
            background: 'oklch(0.99 0.008 75 / 0.92)',
            backdropFilter: 'blur(8px)',
            padding: '11px 15px',
            border: '1px solid oklch(0.9 0.018 70)',
          }}
        >
          <div className="font-display font-bold text-brown-900" style={{ fontSize: '15px' }}>
            Mapa de riesgo · Medellín
          </div>
          <div style={{ fontSize: '11.5px', color: 'oklch(0.55 0.035 55)', marginTop: '2px' }}>
            Toca una zona para ver el detalle
          </div>
        </div>

        {/* LEYENDA flotante */}
        <div
          style={{
            borderRadius: '14px',
            background: 'oklch(0.99 0.008 75 / 0.92)',
            backdropFilter: 'blur(8px)',
            padding: '11px 14px',
            border: '1px solid oklch(0.9 0.018 70)',
            display: 'flex',
            flexDirection: 'column',
            gap: '7px',
          }}
        >
          {Object.entries(RISK_COLORS).map(([level, color]) => (
            <div key={level} style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '11.5px', fontWeight: 500, color: 'oklch(0.4 0.03 50)' }}>
              <span style={{ height: '10px', width: '10px', borderRadius: '99px', background: color, flexShrink: 0 }} />
              {level}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
