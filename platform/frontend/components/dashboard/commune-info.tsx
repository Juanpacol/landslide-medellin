'use client';

import { useEffect, useState } from 'react';
import { fetchRiskExplanation, type CommuneDetail, type CommuneFeature, type RiskExplanationResponse } from '@/lib/api';

type CommuneProps = CommuneFeature['properties'];

export const LEVELS: Record<string, { label: string; color: string; soft: string }> = {
  Bajo:    { label: 'Bajo',    color: 'oklch(0.64 0.11 150)', soft: 'oklch(0.95 0.04 150)' },
  Medio:   { label: 'Medio',   color: 'oklch(0.78 0.13 80)',  soft: 'oklch(0.96 0.05 85)' },
  Alto:    { label: 'Alto',    color: 'oklch(0.66 0.16 50)',  soft: 'oklch(0.95 0.05 55)' },
  Crítico: { label: 'Crítico', color: 'oklch(0.55 0.19 30)',  soft: 'oklch(0.94 0.05 35)' },
};

export const ADVICE: Record<string, string> = {
  Bajo: 'Condiciones estables. Mantén el monitoreo rutinario; no se requieren acciones inmediatas.',
  Medio: 'Vigila la evolución de la lluvia. Revisa canales de drenaje y mantén informada a la comunidad.',
  Alto: 'Activa protocolos preventivos. Inspecciona laderas inestables y coordina con el comité local de riesgo.',
  Crítico: 'Alerta máxima. Considera evacuación preventiva en zonas vulnerables y notifica al DAGRD de inmediato.',
};

const SHADOW = '0 1px 2px oklch(0.5 0.05 50 / 0.04), 0 14px 36px -22px oklch(0.5 0.06 45 / 0.3)';

interface CommuneInfoProps {
  commune: CommuneProps | null;
  detail: CommuneDetail | null;
  loading?: boolean;
  onOpenProfile?: (communeId: string) => void;
}

export function CommuneInfo({ commune, detail, loading = false, onOpenProfile }: CommuneInfoProps) {
  const [explanation, setExplanation] = useState<RiskExplanationResponse | null>(null);

  useEffect(() => {
    if (!commune?.commune_id) { setExplanation(null); return; }
    fetchRiskExplanation(String(commune.commune_id))
      .then(setExplanation)
      .catch(() => setExplanation(null));
  }, [commune?.commune_id]);

  if (!commune) {
    return (
      <div
        style={{
          borderRadius: '24px',
          border: '1px solid oklch(0.9 0.018 70)',
          background: 'oklch(0.99 0.008 75)',
          padding: '22px',
          boxShadow: SHADOW,
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          textAlign: 'center',
          gap: '14px',
        }}
      >
        <div
          style={{
            height: '64px',
            width: '64px',
            borderRadius: '20px',
            background: 'oklch(0.94 0.025 75)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '28px',
          }}
        >
          🗺️
        </div>
        <div>
          <div
            style={{
              fontFamily: 'var(--font-display)',
              fontWeight: 700,
              fontSize: '18px',
              color: 'oklch(0.32 0.04 45)',
            }}
          >
            Selecciona una comuna
          </div>
          <p
            style={{
              fontSize: '13.5px',
              color: 'oklch(0.55 0.035 55)',
              marginTop: '5px',
              maxWidth: '230px',
              lineHeight: 1.5,
            }}
          >
            Toca cualquier zona del mapa para ver su nivel de riesgo y recomendaciones.
          </p>
        </div>
      </div>
    );
  }

  const riskKey: string = commune.categoria_riesgo ?? 'Bajo';
  const level = LEVELS[riskKey] ?? LEVELS['Bajo'];
  const rawScore = (commune.indice_riesgo as number | null | undefined) ?? null;
  const scorePct = rawScore !== null ? Math.round(rawScore * 100) : null;
  const rain = detail?.rainfall_last_7d_total ?? commune.rain7d ?? '—';
  const events = detail?.historical_events?.length ?? ((commune.n_eventos as number | null) ?? '—');
  const advice = ADVICE[riskKey] ?? ADVICE['Bajo'];

  return (
    <div
      className="animate-teyva-rise"
      style={{
        borderRadius: '24px',
        border: '1px solid oklch(0.9 0.018 70)',
        background: 'oklch(0.99 0.008 75)',
        padding: '22px',
        boxShadow: SHADOW,
        height: '100%',
        overflowY: 'auto',
      }}
    >
      {/* Encabezado */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '12px' }}>
        <div>
          <div
            style={{
              fontSize: '11.5px',
              fontWeight: 600,
              textTransform: 'uppercase',
              letterSpacing: '0.12em',
              color: 'oklch(0.55 0.035 55)',
            }}
          >
            Comuna {commune.commune_id}
          </div>
          <div
            style={{
              fontFamily: 'var(--font-display)',
              fontWeight: 700,
              fontSize: '26px',
              letterSpacing: '-0.02em',
              color: 'oklch(0.28 0.04 45)',
              marginTop: '2px',
            }}
          >
            {commune.nombre_comuna}
          </div>
        </div>
        <span
          style={{
            borderRadius: '99px',
            padding: '6px 13px',
            fontSize: '12px',
            fontWeight: 700,
            color: 'oklch(1 0 0)',
            background: level.color,
            flexShrink: 0,
          }}
        >
          {level.label}
        </span>
      </div>

      {/* Barra de riesgo */}
      <div
        style={{
          marginTop: '18px',
          borderRadius: '16px',
          background: level.soft,
          padding: '16px',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            fontSize: '12.5px',
            fontWeight: 600,
            color: 'oklch(0.4 0.04 50)',
          }}
        >
          <span>Índice de riesgo</span>
          <span>{loading ? '…' : scorePct !== null ? `${scorePct}%` : 'Sin datos'}</span>
        </div>
        <div
          style={{
            marginTop: '9px',
            height: '9px',
            borderRadius: '99px',
            background: 'oklch(0.9 0.02 70)',
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              height: '100%',
              width: `${scorePct ?? 0}%`,
              borderRadius: '99px',
              background: level.color,
              transition: 'width 0.4s ease',
            }}
          />
        </div>
      </div>

      {/* Stats */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginTop: '14px' }}>
        <div
          style={{
            borderRadius: '14px',
            border: '1px solid oklch(0.91 0.018 70)',
            padding: '13px 15px',
          }}
        >
          <div style={{ fontSize: '11.5px', color: 'oklch(0.55 0.035 55)', fontWeight: 600 }}>Lluvia 7d</div>
          <div
            style={{
              fontFamily: 'var(--font-display)',
              fontWeight: 700,
              fontSize: '22px',
              color: 'oklch(0.3 0.04 45)',
              marginTop: '3px',
            }}
          >
            {rain} mm
          </div>
        </div>
        <div
          style={{
            borderRadius: '14px',
            border: '1px solid oklch(0.91 0.018 70)',
            padding: '13px 15px',
          }}
        >
          <div style={{ fontSize: '11.5px', color: 'oklch(0.55 0.035 55)', fontWeight: 600 }}>Eventos previos</div>
          <div
            style={{
              fontFamily: 'var(--font-display)',
              fontWeight: 700,
              fontSize: '22px',
              color: 'oklch(0.3 0.04 45)',
              marginTop: '3px',
            }}
          >
            {events}
          </div>
        </div>
      </div>

      {/* Recomendación */}
      <div
        style={{
          marginTop: '16px',
          display: 'flex',
          gap: '9px',
          alignItems: 'flex-start',
          borderRadius: '14px',
          background: 'oklch(0.95 0.02 78)',
          padding: '13px 15px',
        }}
      >
        <span style={{ fontSize: '16px', lineHeight: 1.3, flexShrink: 0 }}>💡</span>
        <p style={{ fontSize: '13px', lineHeight: 1.5, color: 'oklch(0.4 0.04 50)' }}>{advice}</p>
      </div>

      {/* Ver perfil completo */}
      {onOpenProfile && (
        <button
          onClick={() => onOpenProfile(String(commune.commune_id))}
          className="press-scale"
          style={{
            marginTop: '14px',
            width: '100%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '7px',
            padding: '11px 16px',
            borderRadius: '12px',
            border: 'none',
            cursor: 'pointer',
            background: 'var(--gradient-brand)',
            color: 'oklch(0.98 0.01 80)',
            fontFamily: 'var(--font-sans)',
            fontSize: '13.5px',
            fontWeight: 700,
          }}
        >
          Ver perfil completo →
        </button>
      )}

      {/* Explicación generada por IA */}
      {(explanation?.explanation || detail?.model_explanation) && (
        <div
          style={{
            marginTop: '14px',
            borderRadius: '14px',
            border: `1px solid ${level.color}44`,
            padding: '13px 15px',
            background: level.soft,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
            <div style={{ fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'oklch(0.45 0.04 50)' }}>
              Análisis de riesgo
            </div>
            {explanation?.generated_by && (
              <span style={{
                fontSize: '10px', fontWeight: 600, padding: '2px 7px', borderRadius: '99px',
                background: explanation.generated_by === 'template' ? 'oklch(0.92 0.02 70)' : 'oklch(0.92 0.04 145)',
                color: explanation.generated_by === 'template' ? 'oklch(0.5 0.04 55)' : 'oklch(0.38 0.1 145)',
              }}>
                {explanation.generated_by === 'template' ? 'Análisis automático' : '✦ GPT-4 Mini'}
              </span>
            )}
          </div>
          <p style={{ fontSize: '13px', lineHeight: 1.55, color: 'oklch(0.35 0.04 48)', margin: 0 }}>
            {explanation?.explanation ?? detail?.model_explanation}
          </p>
          {explanation?.generated_at && (
            <div style={{ marginTop: '8px', fontSize: '11px', color: 'oklch(0.6 0.03 55)' }}>
              Generado {new Date(explanation.generated_at).toLocaleString('es-CO', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
