'use client';

import { useEffect, useState } from 'react';
import { Droplets } from 'lucide-react';
import { fetchSoilWaterIndex, type SoilWaterIndexEntry } from '@/lib/api';

function swiColor(pct: number | null): string {
  if (pct === null) return 'oklch(0.9 0.01 260)';
  if (pct >= 85) return 'oklch(0.62 0.22 25)'; // rojo
  if (pct >= 60) return 'oklch(0.72 0.12 70)'; // amarillo
  if (pct >= 30) return 'oklch(0.78 0.1 220)'; // azul claro (húmedo, sin riesgo)
  return 'oklch(0.68 0.13 150)'; // verde (seco)
}

export function SoilWaterHeatmap() {
  const [items, setItems] = useState<SoilWaterIndexEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetchSoilWaterIndex()
      .then((d) => {
        if (!cancelled) setItems(d.items);
      })
      .catch(() => {
        if (!cancelled) setItems([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return <div className="text-center py-6 text-sm text-muted-foreground">Cargando saturación del suelo…</div>;
  }

  return (
    <div className="w-full">
      <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-7 gap-2">
        {items.map((it) => (
          <div
            key={it.commune_id}
            className="rounded-xl p-3 flex flex-col items-center gap-1"
            style={{ background: swiColor(it.swi_pct), border: '1px solid var(--border)' }}
            title={`${it.nombre_comuna}: ${it.swi_pct ?? 'sin dato'}% SWI`}
          >
            <Droplets size={14} style={{ opacity: 0.7 }} />
            <div className="text-[11px] font-semibold text-center leading-tight">{it.nombre_comuna}</div>
            <div className="text-sm font-bold">{it.swi_pct !== null ? `${it.swi_pct.toFixed(0)}%` : '—'}</div>
          </div>
        ))}
      </div>
      <div className="flex items-center gap-4 mt-4 text-[11px] text-muted-foreground flex-wrap">
        <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full" style={{ background: 'oklch(0.68 0.13 150)' }} /> Seco (&lt;30%)</span>
        <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full" style={{ background: 'oklch(0.78 0.1 220)' }} /> Húmedo (30-60%)</span>
        <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full" style={{ background: 'oklch(0.72 0.12 70)' }} /> Alto (60-85%)</span>
        <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full" style={{ background: 'oklch(0.62 0.22 25)' }} /> Saturado (&gt;85%)</span>
      </div>
    </div>
  );
}
