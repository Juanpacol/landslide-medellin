'use client';

import { useEffect, useState } from 'react';
import { AlertTriangle, GitBranch, ShieldAlert, Sparkles } from 'lucide-react';
import { Progress } from '@/components/ui/progress';
import { Skeleton } from '@/components/ui/skeleton';
import { fetchDerivation, type DerivationResponse } from '@/lib/api';

interface DerivationPanelProps {
  communeId: string;
}

/** Neuro-symbolic derivation panel: neural score, fired rules, conflict
 *  overrides and confidence — renders application/neurosymbolic/infer.py's
 *  Verdict.derivation (specs/003-inference-engine/, specs/004-explanations/).
 *  Every line here traces to a derivation node; nothing is narrated by an LLM. */
export function DerivationPanel({ communeId }: DerivationPanelProps) {
  const [data, setData] = useState<DerivationResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchDerivation(communeId)
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch(() => {
        if (!cancelled) setData(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [communeId]);

  if (loading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <Skeleton style={{ height: '16px', width: '60%' }} />
        <Skeleton style={{ height: '40px' }} />
        <Skeleton style={{ height: '40px' }} />
      </div>
    );
  }

  const derivation = data?.derivation;
  if (!data || !derivation) {
    return (
      <div style={{ fontSize: '12px', color: 'var(--muted-foreground)' }}>
        Sin derivación disponible para esta comuna todavía.
      </div>
    );
  }

  const confidencePct = data.confidence !== null && data.confidence !== undefined ? Math.round(data.confidence * 100) : null;
  const hasConflicts = (data.conflicts ?? []).length > 0;
  const isInsufficientData = data.display.status === 'insufficient_data';

  return (
    <div style={{ fontSize: '12px', color: 'var(--foreground)', lineHeight: 1.6 }}>
      {/* Mutually-exclusive headline: a trustworthy estimate, OR insufficient data + cause —
          never both (docs/research/audit-2026-07.md §5). */}
      {data.display.status === 'insufficient_data' ? (
        <div
          style={{
            marginBottom: '12px',
            padding: '10px 12px',
            borderRadius: '8px',
            background: 'oklch(0.95 0.08 25 / 0.3)',
            border: '1px solid oklch(0.9 0.15 25)',
            display: 'flex',
            gap: '8px',
            fontSize: '12px',
            color: 'oklch(0.4 0.15 25)',
          }}
        >
          <ShieldAlert size={16} style={{ flexShrink: 0, marginTop: '2px' }} />
          <span>
            <strong>Datos insuficientes</strong> — {data.display.reason}. Ausencia de dato ≠
            ausencia de riesgo: no se muestra un nivel numérico porque la señal disponible no es
            confiable, en vez de estimar sobre un dato roto.
          </span>
        </div>
      ) : (
        <div
          style={{
            marginBottom: '12px',
            padding: '10px 12px',
            borderRadius: '8px',
            background: 'var(--muted)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 700, marginBottom: '4px' }}>
            <Sparkles size={14} />
            Score neuronal:{' '}
            {derivation.neural_score !== null ? `${(derivation.neural_score * 100).toFixed(1)}%` : '—'} (
            {derivation.neural_level})
          </div>
          {data.priority && data.priority !== 'normal' && (
            <div style={{ fontSize: '11px', color: 'var(--muted-foreground)' }}>
              Prioridad operativa: <strong>{data.priority}</strong>
            </div>
          )}
        </div>
      )}

      {/* Fired rules */}
      <div style={{ marginBottom: '12px' }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            fontSize: '11px',
            fontWeight: 700,
            color: 'var(--muted-foreground)',
            marginBottom: '6px',
          }}
        >
          <GitBranch size={13} />
          REGLAS ACTIVADAS ({derivation.fired_rules.length})
        </div>
        {derivation.fired_rules.length === 0 ? (
          <div style={{ fontSize: '11px', color: 'var(--muted-foreground)' }}>
            Ninguna regla geotécnica se activó — el nivel viene solo del score neuronal.
          </div>
        ) : (
          <ul style={{ paddingLeft: '16px', margin: 0, fontSize: '11px' }}>
            {derivation.fired_rules.map((rule) => (
              <li key={rule.id} style={{ marginBottom: '4px' }}>
                <strong>{rule.id}</strong> — {rule.description}
                <div style={{ color: 'var(--muted-foreground)', fontSize: '10px' }}>{rule.provenance}</div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Conflicts / overrides */}
      {hasConflicts && (
        <div style={{ marginBottom: '12px' }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              fontSize: '11px',
              fontWeight: 700,
              color: 'var(--muted-foreground)',
              marginBottom: '6px',
            }}
          >
            <AlertTriangle size={13} />
            CONFLICTOS RESUELTOS
          </div>
          <ul style={{ paddingLeft: '16px', margin: 0, fontSize: '11px' }}>
            {data.conflicts.map((c, i) => (
              <li key={`${c.rule_id}-${i}`} style={{ marginBottom: '4px' }}>
                <strong>{c.rule_id}</strong> ({c.effect})
                {c.neural_level && c.resolved_level && (
                  <>
                    : {c.neural_level} → {c.resolved_level}
                  </>
                )}
                {c.reason && <>: {c.reason}</>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Calibration note */}
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
        {derivation.calibration_note}
      </div>

      {!isInsufficientData && confidencePct !== null && (
        <div style={{ marginTop: '12px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginBottom: '4px' }}>
            <span style={{ color: 'var(--muted-foreground)' }}>Confianza (esta corrida)</span>
            <strong>{confidencePct}%</strong>
          </div>
          <Progress value={confidencePct} />
        </div>
      )}
    </div>
  );
}
