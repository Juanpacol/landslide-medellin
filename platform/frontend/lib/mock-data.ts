// Archivo mantenido solo para compatibilidad de tipos legacy
// Los datos reales vienen de /api/* via static/lib/api.ts

export type RiskLevel = 'Bajo' | 'Medio' | 'Alto' | 'Crítico';

export const riskColors: Record<RiskLevel, string> = {
  'Bajo': '#22c55e',
  'Medio': '#eab308',
  'Alto': '#f97316',
  'Crítico': '#ef4444',
};
