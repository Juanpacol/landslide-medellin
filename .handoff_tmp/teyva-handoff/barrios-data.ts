import type { Comuna, RiskLevel } from "@/lib/teyva-data";
import { COMUNAS } from "@/lib/teyva-data";
import barriosGeo from "@/lib/barrios-medellin.json";
import type { Feature, FeatureCollection, Geometry } from "geojson";

export interface BarrioProps {
  codigo: string;
  nombre: string;
  comuna: string;
  municipio?: string;
}

export interface Barrio {
  id: string;            // codigo
  name: string;
  comunaId: number;
  comunaName: string;
  municipio: string;
  riskLevel: RiskLevel;
  riskScore: number;
  events: number;
  hillside: boolean;
  rain7d: number;
  rain30d: number;
  trend: number;
  lastPrediction: string;
  modelVersion: string;
  explanation: string;
}

const FC = barriosGeo as unknown as FeatureCollection<Geometry, BarrioProps>;
const COMUNA_BY_ID = new Map(COMUNAS.map((c) => [c.id, c]));

// Hash determinista para variar valores por barrio sin aleatoriedad real
function hash(str: string): number {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return (h >>> 0) / 0xffffffff; // 0..1
}

function bumpLevel(level: RiskLevel, delta: number): RiskLevel {
  const order: RiskLevel[] = ["Bajo", "Medio", "Alto", "Crítico"];
  const idx = Math.max(0, Math.min(3, order.indexOf(level) + delta));
  return order[idx];
}

function buildBarrio(f: Feature<Geometry, BarrioProps>): Barrio | null {
  const p = f.properties;
  if (!p) return null;
  const municipio = p.municipio || "Medellín";
  const r = hash(p.codigo + p.nombre);

  // Para Medellín tomamos la comuna real; para Bello generamos perfil sintético.
  const comunaIdRaw = parseInt(p.comuna, 10);
  const c = Number.isFinite(comunaIdRaw) ? COMUNA_BY_ID.get(comunaIdRaw) : undefined;

  const baseScore = c ? c.riskScore : 0.35 + r * 0.45;
  const baseLevel: RiskLevel = c
    ? c.riskLevel
    : baseScore > 0.8
      ? "Crítico"
      : baseScore > 0.6
        ? "Alto"
        : baseScore > 0.35
          ? "Medio"
          : "Bajo";
  const baseRain7 = c ? c.rain7d : 95 + Math.round(r * 50);
  const baseRain30 = c ? c.rain30d : 280 + Math.round(r * 120);
  const baseEvents = c ? c.events : Math.round(r * 12);
  const baseTrend = c ? c.trend : Math.round((r - 0.4) * 20);
  const baseHillside = c ? c.hillside : r > 0.45;
  const comunaId = c ? c.id : 100 + (Math.floor(r * 4)); // 100-103 sintético para Bello
  const comunaName = c ? c.name : "Bello (zona)";

  // Pequeñas variaciones alrededor del riesgo de la comuna
  const score = Math.max(0.05, Math.min(0.98, baseScore + (r - 0.5) * 0.18));
  let level: RiskLevel = baseLevel;
  if (r > 0.85) level = bumpLevel(level, 1);
  else if (r < 0.15) level = bumpLevel(level, -1);

  const rain7d = Math.round(baseRain7 * (0.85 + r * 0.3));
  const rain30d = Math.round(baseRain30 * (0.85 + r * 0.3));
  const events = Math.max(0, Math.round((baseEvents * (0.4 + r * 0.7)) / 4));
  const trend = Math.round(baseTrend + (r - 0.5) * 8);

  return {
    id: p.codigo,
    name: p.nombre || p.codigo,
    comunaId,
    comunaName,
    municipio,
    riskLevel: level,
    riskScore: score,
    events,
    hillside: baseHillside && r > 0.25,
    rain7d,
    rain30d,
    trend,
    lastPrediction: "Hace 12 min",
    modelVersion: "teyva-risk v2.4.1",
    explanation:
      level === "Crítico"
        ? `Barrio en ladera con ${rain7d}mm acumulados en 7 días. Suelo saturado y pendiente pronunciada — vigilancia prioritaria.`
        : level === "Alto"
          ? `Precipitación sostenida (${rain7d}mm/7d) sobre terreno susceptible. Histórico de movimientos en el sector.`
          : level === "Medio"
            ? `Condiciones moderadas. Lluvia dentro del promedio y sin eventos recientes significativos en el barrio.`
            : `Bajo riesgo. Suelos estables, baja precipitación y sin reportes en los últimos 30 días.`,
  };
}

export const BARRIOS: Barrio[] = FC.features
  .map(buildBarrio)
  .filter((b): b is Barrio => b !== null);

export const BARRIO_BY_ID = new Map(BARRIOS.map((b) => [b.id, b]));

// Adaptador: convierte un Barrio a Comuna para reutilizar el panel ComunaDetail
export function barrioAsComuna(b: Barrio): Comuna {
  return {
    id: b.comunaId,
    name: `${b.name}`,
    nickname: `Barrio · ${b.municipio} · ${b.comunaName}`,
    riskLevel: b.riskLevel,
    riskScore: b.riskScore,
    events: b.events,
    hillside: b.hillside,
    rain7d: b.rain7d,
    rain30d: b.rain30d,
    trend: b.trend,
    lastPrediction: b.lastPrediction,
    modelVersion: b.modelVersion,
    explanation: b.explanation,
    center: [0, 0],
  };
}
