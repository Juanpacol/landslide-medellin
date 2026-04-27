export type RiskLevel = "Bajo" | "Medio" | "Alto" | "Crítico";

export interface Comuna {
  id: number;
  name: string;
  nickname: string;
  riskLevel: RiskLevel;
  riskScore: number;
  events: number;
  hillside: boolean;
  rain7d: number;
  rain30d: number;
  trend: number; // % vs semana anterior
  lastPrediction: string;
  modelVersion: string;
  explanation: string;
  // bbox aproximado (lng,lat) → polígono romboidal estilizado para el mapa
  center: [number, number];
}

const RAW: Omit<Comuna, "explanation" | "lastPrediction" | "modelVersion">[] = [
  { id: 1, name: "Popular", nickname: "Comuna 1", riskLevel: "Crítico", riskScore: 0.91, events: 24, hillside: true, rain7d: 142, rain30d: 410, trend: 18, center: [-75.546, 6.295] },
  { id: 2, name: "Santa Cruz", nickname: "Comuna 2", riskLevel: "Alto", riskScore: 0.78, events: 17, hillside: true, rain7d: 121, rain30d: 365, trend: 9, center: [-75.555, 6.290] },
  { id: 3, name: "Manrique", nickname: "Comuna 3", riskLevel: "Alto", riskScore: 0.74, events: 15, hillside: true, rain7d: 118, rain30d: 348, trend: 7, center: [-75.553, 6.275] },
  { id: 4, name: "Aranjuez", nickname: "Comuna 4", riskLevel: "Medio", riskScore: 0.52, events: 8, hillside: false, rain7d: 96, rain30d: 290, trend: -3, center: [-75.563, 6.273] },
  { id: 5, name: "Castilla", nickname: "Comuna 5", riskLevel: "Medio", riskScore: 0.48, events: 6, hillside: false, rain7d: 88, rain30d: 270, trend: -5, center: [-75.580, 6.290] },
  { id: 6, name: "Doce de Octubre", nickname: "Comuna 6", riskLevel: "Alto", riskScore: 0.71, events: 12, hillside: true, rain7d: 110, rain30d: 330, trend: 11, center: [-75.585, 6.300] },
  { id: 7, name: "Robledo", nickname: "Comuna 7", riskLevel: "Medio", riskScore: 0.55, events: 9, hillside: true, rain7d: 99, rain30d: 295, trend: 2, center: [-75.605, 6.282] },
  { id: 8, name: "Villa Hermosa", nickname: "Comuna 8", riskLevel: "Crítico", riskScore: 0.88, events: 21, hillside: true, rain7d: 138, rain30d: 395, trend: 22, center: [-75.545, 6.255] },
  { id: 9, name: "Buenos Aires", nickname: "Comuna 9", riskLevel: "Alto", riskScore: 0.69, events: 13, hillside: true, rain7d: 108, rain30d: 320, trend: 6, center: [-75.555, 6.245] },
  { id: 10, name: "La Candelaria", nickname: "Comuna 10", riskLevel: "Bajo", riskScore: 0.22, events: 2, hillside: false, rain7d: 70, rain30d: 220, trend: -8, center: [-75.572, 6.247] },
  { id: 11, name: "Laureles-Estadio", nickname: "Comuna 11", riskLevel: "Bajo", riskScore: 0.18, events: 1, hillside: false, rain7d: 65, rain30d: 210, trend: -10, center: [-75.595, 6.247] },
  { id: 12, name: "La América", nickname: "Comuna 12", riskLevel: "Medio", riskScore: 0.41, events: 5, hillside: false, rain7d: 82, rain30d: 255, trend: 1, center: [-75.610, 6.245] },
  { id: 13, name: "San Javier", nickname: "Comuna 13", riskLevel: "Alto", riskScore: 0.76, events: 16, hillside: true, rain7d: 125, rain30d: 358, trend: 14, center: [-75.620, 6.250] },
  { id: 14, name: "El Poblado", nickname: "Comuna 14", riskLevel: "Bajo", riskScore: 0.20, events: 2, hillside: true, rain7d: 72, rain30d: 230, trend: -6, center: [-75.568, 6.210] },
  { id: 15, name: "Guayabal", nickname: "Comuna 15", riskLevel: "Bajo", riskScore: 0.28, events: 3, hillside: false, rain7d: 76, rain30d: 240, trend: -2, center: [-75.590, 6.200] },
  { id: 16, name: "Belén", nickname: "Comuna 16", riskLevel: "Medio", riskScore: 0.46, events: 7, hillside: true, rain7d: 92, rain30d: 280, trend: 4, center: [-75.610, 6.215] },
];

export const COMUNAS: Comuna[] = RAW.map((c) => ({
  ...c,
  lastPrediction: "Hace 12 min",
  modelVersion: "teyva-risk v2.4.1",
  explanation:
    c.riskLevel === "Crítico"
      ? `Riesgo elevado por lluvias acumuladas (${c.rain7d}mm en 7 días) sobre laderas con eventos previos. Saturación del suelo y pendientes pronunciadas.`
      : c.riskLevel === "Alto"
        ? `Combinación de precipitación sostenida y zona de ladera con histórico de movimientos. Vigilancia recomendada.`
        : c.riskLevel === "Medio"
          ? `Condiciones moderadas. Lluvia dentro del promedio mensual; sin eventos recientes significativos.`
          : `Bajo riesgo. Suelos estables, baja precipitación y sin eventos reportados en los últimos 30 días.`,
}));

export const RISK_COLORS: Record<RiskLevel, string> = {
  Bajo: "var(--risk-low)",
  Medio: "var(--risk-medium)",
  Alto: "var(--risk-high)",
  Crítico: "var(--risk-critical)",
};

export function riskTextClass(level: RiskLevel) {
  return {
    Bajo: "text-[oklch(0.45_0.12_150)] dark:text-[oklch(0.78_0.14_150)]",
    Medio: "text-[oklch(0.55_0.15_85)] dark:text-[oklch(0.85_0.15_95)]",
    Alto: "text-[oklch(0.55_0.17_50)] dark:text-[oklch(0.78_0.17_50)]",
    Crítico: "text-[oklch(0.50_0.22_25)] dark:text-[oklch(0.72_0.22_25)]",
  }[level];
}

/** Genera un polígono hexagonal estilizado alrededor del centro para mapearlo en Leaflet. */
export function comunaPolygon(center: [number, number], size = 0.011): [number, number][] {
  const [lng, lat] = center;
  const pts: [number, number][] = [];
  for (let i = 0; i < 6; i++) {
    const a = (Math.PI / 3) * i + Math.PI / 6;
    pts.push([lat + Math.sin(a) * size, lng + Math.cos(a) * size * 1.4]);
  }
  return pts;
}