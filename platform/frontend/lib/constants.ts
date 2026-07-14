// Constantes de la aplicación TEYVA

export const TEYVA_RISK_LEVELS = {
  BAJO: 'Bajo',
  MEDIO: 'Medio',
  ALTO: 'Alto',
  CRITICO: 'Crítico',
} as const;

export const TEYVA_COLORS = {
  // Paleta tierra cálida
  brand: 'oklch(0.58 0.14 42)',           // Terracota
  brandDeep: 'oklch(0.45 0.10 38)',       // Terracota oscura
  gold: 'oklch(0.82 0.14 78)',            // Dorado
  
  // Estados de riesgo
  risk: {
    bajo: 'oklch(0.64 0.11 150)',         // Verde
    medio: 'oklch(0.78 0.13 80)',         // Ocre/Amarillo
    alto: 'oklch(0.66 0.16 50)',          // Naranja
    critico: 'oklch(0.55 0.19 30)',       // Rojo-terracota
  },
  riskSoft: {
    bajo: 'oklch(0.95 0.04 150)',
    medio: 'oklch(0.96 0.05 85)',
    alto: 'oklch(0.95 0.05 55)',
    critico: 'oklch(0.94 0.05 35)',
  },
  
  // Neutral
  background: 'oklch(0.96 0.014 75)',
  card: 'oklch(0.99 0.008 75)',
  foreground: 'oklch(0.26 0.035 45)',
  muted: 'oklch(0.52 0.035 55)',
  border: 'oklch(0.90 0.018 70)',
} as const;

export const COMUNAS_MEDELLIN = [
  { id: '1', nombre: 'Popular' },
  { id: '2', nombre: 'Santa Cruz' },
  { id: '3', nombre: 'Manrique' },
  { id: '4', nombre: 'Aranjuez' },
  { id: '5', nombre: 'Castilla' },
  { id: '6', nombre: 'Doce de Octubre' },
  { id: '7', nombre: 'Robledo' },
  { id: '8', nombre: 'Villa Hermosa' },
  { id: '9', nombre: 'Buenos Aires' },
  { id: '10', nombre: 'La Candelaria' },
  { id: '11', nombre: 'Laureles' },
  { id: '12', nombre: 'La América' },
  { id: '13', nombre: 'San Javier' },
  { id: '14', nombre: 'El Poblado' },
  { id: '15', nombre: 'Guayabal' },
  { id: '16', nombre: 'Belén' },
] as const;
