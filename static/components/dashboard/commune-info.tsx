'use client';

import { CalendarClock, CloudRain, Cpu, Mountain, TrendingDown, TrendingUp } from 'lucide-react';
import type { CommuneDetail, CommuneFeature } from '@/lib/api';

type CommuneProps = CommuneFeature['properties'];

const riskColors: Record<string, string> = {
  'Bajo': '#22c55e',
  'Medio': '#eab308',
  'Alto': '#ea7a21',
  'Crítico': '#e11d48',
};

interface CommuneInfoProps {
  commune: CommuneProps | null;
  detail: CommuneDetail | null;
  loading?: boolean;
}

export function CommuneInfo({ commune, detail, loading = false }: CommuneInfoProps) {
  if (!commune) {
    return (
      <div className="flex h-full flex-col items-center justify-center rounded-3xl border border-dashed border-border bg-card/40 p-8 text-center">
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-[image:var(--gradient-leaf)] opacity-80">
          <Mountain className="h-6 w-6 text-white" />
        </div>
        <h3 className="mt-4 font-display text-lg font-semibold text-foreground">Selecciona un barrio</h3>
        <p className="mt-1 max-w-xs text-sm text-muted-foreground">
          Haz click en cualquier poligono del mapa para ver el detalle del riesgo, precipitacion acumulada y explicacion
          del modelo TEYVA.
        </p>
      </div>
    );
  }

  const riskColor = riskColors[commune.categoria_riesgo] ?? '#22c55e';
  const trend = Number.isFinite(Number(commune.trend))
    ? Number(commune.trend)
    : Math.round((Number(commune.indice_riesgo ?? 0) - 0.5) * 100);
  const TrendIcon = trend >= 0 ? TrendingUp : TrendingDown;
  const comunaNombre = commune.comuna_nombre ?? `Comuna ${commune.commune_id}`;
  const municipio = commune.municipio ?? 'Medellin';

  const modelExplanation = detail?.model_explanation || 'Sin datos';
  const rain7d = detail?.rainfall_last_7d_total ?? commune.rain7d ?? 'Sin datos';
  const rain30d = detail?.rainfall_last_30d_total ?? commune.rain30d ?? 'Sin datos';
  const eventsCount = detail?.historical_events?.length ?? commune.n_eventos ?? 'Sin datos';
  const zonaLadera = detail?.is_zona_ladera ?? commune.is_zona_ladera;
  const riskText = detail?.risk_level || commune.categoria_riesgo || 'Sin datos';

  return (
    <div className="flex h-full flex-col overflow-y-auto rounded-3xl border border-border/60 bg-card shadow-[var(--shadow-soft)]">
      <div
        className="relative overflow-visible px-6 py-5"
        style={{
          background: `linear-gradient(135deg, color-mix(in oklab, ${riskColor} 16%, transparent), transparent 72%)`,
        }}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1 pr-2">
            <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
              {comunaNombre} · {municipio}
            </div>
            <h2 className="mt-1 whitespace-normal break-words font-display text-3xl font-semibold leading-tight tracking-tight text-foreground">
              {commune.nombre_comuna}
            </h2>
          </div>
          <span
            className="mt-1 shrink-0 rounded-full border px-3 py-1 text-xs font-semibold"
            style={{
              borderColor: `color-mix(in oklab, ${riskColor} 48%, transparent)`,
              background: `color-mix(in oklab, ${riskColor} 12%, transparent)`,
              color: riskColor,
            }}
          >
            Riesgo {riskText}
          </span>
        </div>

        <div className="mt-4 flex items-end gap-3">
          <div className="font-display text-5xl font-semibold leading-none tracking-tight text-foreground">
            {Math.round(Number(commune.indice_riesgo ?? 0) * 100)}
            <span className="text-2xl text-muted-foreground">%</span>
          </div>
          <div className="mb-1 flex items-center gap-1 text-xs font-medium text-muted-foreground">
            <TrendIcon className={`h-3.5 w-3.5 ${trend >= 0 ? 'text-[var(--floral)]' : 'text-[var(--leaf)]'}`} />
            {trend > 0 ? '+' : ''}
            {trend}% tendencia estimada
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 px-6 pb-2">
        <Stat icon={<CloudRain className="h-3.5 w-3.5" />} label="Lluvia 7d" value={`${rain7d} mm`} />
        <Stat icon={<CloudRain className="h-3.5 w-3.5" />} label="Lluvia 30d" value={`${rain30d} mm`} />
        <Stat icon={<Mountain className="h-3.5 w-3.5" />} label="Zona de ladera" value={zonaLadera ? 'Si' : 'No'} />
        <Stat icon={<TrendingUp className="h-3.5 w-3.5" />} label="Eventos recientes" value={String(eventsCount)} />
      </div>

      <div className="mx-6 mt-4 rounded-2xl bg-muted/60 p-4">
        <div className="text-[11px] font-semibold tracking-wider text-muted-foreground">Explicación del modelo</div>
        <p className="mt-1.5 text-sm leading-relaxed text-foreground">
          {loading ? 'Cargando detalle de la comuna...' : modelExplanation}
        </p>
      </div>

      <div className="mt-auto flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-border/60 px-6 py-3 text-[11px] text-muted-foreground">
        <div className="flex items-center gap-1.5">
          <CalendarClock className="h-3 w-3" /> Actualizado recientemente
        </div>
        <div className="flex items-center gap-1.5">
          <Cpu className="h-3 w-3" /> teyva-risk v2.4.1
        </div>
      </div>
    </div>
  );
}

function Stat({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-2xl border border-border/70 bg-background/45 p-3">
      <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
        {icon}
        {label}
      </div>
      <div className="mt-1 font-display text-lg font-semibold text-foreground">{value}</div>
    </div>
  );
}
