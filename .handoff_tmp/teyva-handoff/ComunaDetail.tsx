import {
  CalendarClock,
  CloudRain,
  Cpu,
  Mountain,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import type { Comuna } from "@/lib/teyva-data";
import { RISK_COLORS, riskTextClass } from "@/lib/teyva-data";

export function ComunaDetail({ comuna }: { comuna: Comuna | null }) {
  if (!comuna) {
    return (
      <div className="flex h-full flex-col items-center justify-center rounded-3xl border border-dashed border-border bg-card/40 p-8 text-center">
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-[image:var(--gradient-leaf)] opacity-80">
          <Mountain className="h-6 w-6 text-white" />
        </div>
        <h3 className="mt-4 font-display text-lg font-600 text-foreground">
          Selecciona una comuna
        </h3>
        <p className="mt-1 max-w-xs text-sm text-muted-foreground">
          Haz click en cualquier polígono del mapa para ver el detalle del riesgo,
          precipitación acumulada y la explicación del modelo TEYVA.
        </p>
      </div>
    );
  }

  const TrendIcon = comuna.trend >= 0 ? TrendingUp : TrendingDown;

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-3xl border border-border/60 bg-card shadow-[var(--shadow-soft)]">
      {/* Header */}
      <div
        className="relative overflow-hidden p-5"
        style={{
          background: `linear-gradient(135deg, color-mix(in oklab, ${RISK_COLORS[comuna.riskLevel]} 22%, transparent), transparent 70%)`,
        }}
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
              {comuna.nickname}
            </div>
            <h2 className="mt-1 font-display text-2xl font-700 leading-tight text-foreground">
              {comuna.name}
            </h2>
          </div>
          <span
            className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${riskTextClass(comuna.riskLevel)}`}
            style={{
              borderColor: `color-mix(in oklab, ${RISK_COLORS[comuna.riskLevel]} 40%, transparent)`,
              background: `color-mix(in oklab, ${RISK_COLORS[comuna.riskLevel]} 14%, transparent)`,
            }}
          >
            Riesgo {comuna.riskLevel}
          </span>
        </div>

        <div className="mt-4 flex items-end gap-3">
          <div className="font-display text-5xl font-700 leading-none tracking-tight text-foreground">
            {(comuna.riskScore * 100).toFixed(0)}
            <span className="text-2xl text-muted-foreground">%</span>
          </div>
          <div className="mb-1 flex items-center gap-1 text-xs font-medium text-muted-foreground">
            <TrendIcon
              className={`h-3.5 w-3.5 ${comuna.trend >= 0 ? "text-[var(--floral)]" : "text-[var(--leaf)]"}`}
            />
            {comuna.trend > 0 ? "+" : ""}
            {comuna.trend}% vs semana anterior
          </div>
        </div>
      </div>

      {/* Métricas */}
      <div className="grid grid-cols-2 gap-3 px-5 pb-2">
        <Stat
          icon={<CloudRain className="h-3.5 w-3.5" />}
          label="Lluvia 7d"
          value={`${comuna.rain7d} mm`}
        />
        <Stat
          icon={<CloudRain className="h-3.5 w-3.5" />}
          label="Lluvia 30d"
          value={`${comuna.rain30d} mm`}
        />
        <Stat
          icon={<Mountain className="h-3.5 w-3.5" />}
          label="Zona de ladera"
          value={comuna.hillside ? "Sí" : "No"}
        />
        <Stat
          icon={<TrendingUp className="h-3.5 w-3.5" />}
          label="Eventos acumulados"
          value={String(comuna.events)}
        />
      </div>

      {/* Explicación */}
      <div className="mx-5 mt-3 rounded-2xl bg-muted/60 p-4">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          Explicación del modelo
        </div>
        <p className="mt-1.5 text-sm leading-relaxed text-foreground">
          {comuna.explanation}
        </p>
      </div>

      {/* Footer meta */}
      <div className="mt-auto flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-border/60 px-5 py-3 text-[11px] text-muted-foreground">
        <div className="flex items-center gap-1.5">
          <CalendarClock className="h-3 w-3" /> {comuna.lastPrediction}
        </div>
        <div className="flex items-center gap-1.5">
          <Cpu className="h-3 w-3" /> {comuna.modelVersion}
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
    <div className="rounded-xl border border-border/60 bg-background/40 p-3">
      <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
        {icon}
        {label}
      </div>
      <div className="mt-1 font-display text-lg font-600 text-foreground">
        {value}
      </div>
    </div>
  );
}