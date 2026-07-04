'use client';

import { AlertTriangle } from 'lucide-react';
import type { CommuneFeature } from '@/lib/api';

interface AlertBannerProps {
  communes: CommuneFeature['properties'][];
}

export function AlertBanner({ communes }: AlertBannerProps) {
  const criticals = communes.filter((c) => c.categoria_riesgo === 'Crítico');
  const highs = communes.filter((c) => c.categoria_riesgo === 'Alto');
  const total = criticals.length + highs.length;

  if (total === 0) {
    return null;
  }

  return (
    <div
      style={{
        borderRadius: '16px',
        border: '1px solid oklch(0.90 0.02 50)',
        background: 'linear-gradient(135deg, oklch(0.94 0.05 35) 0%, oklch(0.92 0.04 40) 100%)',
        padding: '16px 20px',
        display: 'flex',
        alignItems: 'center',
        gap: '14px',
      }}
    >
      <div
        style={{
          display: 'flex',
          height: '40px',
          width: '40px',
          borderRadius: '12px',
          background: 'oklch(0.55 0.19 30)',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
        }}
      >
        <AlertTriangle className="h-5 w-5 text-white" />
      </div>
      <div style={{ flex: 1 }}>
        <div
          style={{
            fontFamily: 'var(--font-display)',
            fontWeight: 700,
            fontSize: '15px',
            color: 'oklch(0.28 0.04 45)',
          }}
        >
          {total} {total === 1 ? 'zona' : 'zonas'} en alerta
        </div>
        <div style={{ fontSize: '13px', marginTop: '2px', color: 'oklch(0.4 0.04 50)' }}>
          {criticals.length > 0 && (
            <>
              <strong>{criticals.length}</strong> {criticals.length === 1 ? 'crítica' : 'críticas'}
              {highs.length > 0 && ' · '}
            </>
          )}
          {highs.length > 0 && (
            <>
              <strong>{highs.length}</strong> {highs.length === 1 ? 'alta' : 'altas'}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
