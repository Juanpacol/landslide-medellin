import {
  AlertTriangle,
  CloudRain,
  Database,
  Layers,
  ShieldAlert,
  TrendingUp,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { COMUNAS } from "@/lib/teyva-data";

interface Kpi {
  label: string;
  value: string;
  hint: string;
  tone: "leaf" | "sun" | "floral" | "river" | "critical" | "earth";
  icon: LucideIcon;
  tooltip: string;
}

const toneStyles: Record<Kpi["tone"], string> = {
  leaf: "bg-[oklch(0.95_0.04_150)] text-[oklch(0.40_0.10_158)] dark:bg-[oklch(0.30_0.04_158)] dark:text-[oklch(0.85_0.10_150)]",
  sun: "bg-[oklch(0.96_0.06_90)] text-[oklch(0.45_0.12_85)] dark:bg-[oklch(0.30_0.05_90)] dark:text-[oklch(0.88_0.13_90)]",
  floral: "bg-[oklch(0.95_0.06_55)] text-[oklch(0.50_0.15_50)] dark:bg-[oklch(0.30_0.06_55)] dark:text-[oklch(0.82_0.15_55)]",
  river: "bg-[oklch(0.95_0.05_235)] text-[oklch(0.45_0.13_235)] dark:bg-[oklch(0.28_0.05_235)] dark:text-[oklch(0.80_0.13_235)]",
  critical: "bg-[oklch(0.95_0.06_25)] text-[oklch(0.50_0.20_25)] dark:bg-[oklch(0.30_0.07_25)] dark:text-[oklch(0.80_0.18_25)]",
  earth: "bg-[oklch(0.94_0.04_60)] text-[oklch(0.45_0.10_55)] dark:bg-[oklch(0.30_0.04_60)] dark:text-[oklch(0.82_0.10_60)]",
};

export function KpiCards() {
  const total = COMUNAS.length;
  const critical = COMUNAS.filter((c) => c.riskLevel === "Crítico").length;
  const high = COMUNAS.filter((c) => c.riskLevel === "Alto").length;
  const events = COMUNAS.reduce((s, c) => s + c.events, 0);
  const trend = Math.round(
    COMUNAS.reduce((s, c) => s + c.trend, 0) / COMUNAS.length,
  );

  const kpis: Kpi[] = [
    {
      label: "Comunas monitoreadas",
      value: String(total),
      hint: "cobertura total",
      tone: "leaf",
      icon: Layers,
      tooltip: "Número de comunas con datos en tiempo real.",
    },
    {
      label: "Riesgo crítico",
      value: String(critical),
      hint: "acción inmediata",
      tone: "critical",
      icon: ShieldAlert,
      tooltip: "Comunas con índice de riesgo > 0.85.",
    },
    {
      label: "Riesgo alto",
      value: String(high),
      hint: "vigilancia activa",
      tone: "floral",
      icon: AlertTriangle,
      tooltip: "Comunas con índice de riesgo entre 0.65 y 0.85.",
    },
    {
      label: "Eventos recientes",
      value: String(events),
      hint: "últimos 30 días",
      tone: "earth",
      icon: CloudRain,
      tooltip: "Total acumulado de eventos reportados.",
    },
    {
      label: "Tendencia semanal",
      value: `${trend > 0 ? "+" : ""}${trend}%`,
      hint: trend > 0 ? "incremento" : "descenso",
      tone: "sun",
      icon: TrendingUp,
      tooltip: "Variación promedio del índice vs. semana anterior.",
    },
    {
      label: "Calidad de datos",
      value: "97%",
      hint: "completitud",
      tone: "river",
      icon: Database,
      tooltip: "Porcentaje de variables con dato válido en la última corrida.",
    },
  ];

  return (
    <section
      aria-label="Resumen ejecutivo"
      className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6"
    >
      {kpis.map((k) => {
        const Icon = k.icon;
        return (
          <div
            key={k.label}
            title={k.tooltip}
            className="group relative overflow-hidden rounded-2xl border border-border/60 bg-card p-4 shadow-[var(--shadow-soft)] transition-all hover:-translate-y-0.5 hover:shadow-[var(--shadow-elevated)]"
          >
            <div className="flex items-start justify-between">
              <div
                className={`flex h-9 w-9 items-center justify-center rounded-xl ${toneStyles[k.tone]}`}
              >
                <Icon className="h-4 w-4" />
              </div>
            </div>
            <div className="mt-4 font-display text-3xl font-600 leading-none tracking-tight text-foreground">
              {k.value}
            </div>
            <div className="mt-2 text-sm font-medium text-foreground">
              {k.label}
            </div>
            <div className="mt-0.5 text-xs text-muted-foreground">{k.hint}</div>
            <div
              aria-hidden
              className="pointer-events-none absolute -bottom-12 -right-12 h-32 w-32 rounded-full bg-[image:var(--gradient-leaf)] opacity-[0.04] blur-2xl transition-opacity group-hover:opacity-[0.10]"
            />
          </div>
        );
      })}
    </section>
  );
}