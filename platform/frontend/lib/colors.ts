// Paleta Teyva — Colores en OKLCH
export const TEYVA_COLORS = {
  // Tierra cálida
  brown: {
    50: 'oklch(0.97 0.008 35)',
    100: 'oklch(0.93 0.016 35)',
    200: 'oklch(0.88 0.022 35)',
    300: 'oklch(0.82 0.032 38)',
    400: 'oklch(0.74 0.046 42)',
    500: 'oklch(0.62 0.078 45)',
    600: 'oklch(0.48 0.078 48)',
    700: 'oklch(0.38 0.068 48)',
    900: 'oklch(0.26 0.04 38)',
  },
  terracotta: {
    50: 'oklch(0.96 0.01 50)',
    100: 'oklch(0.92 0.018 50)',
    200: 'oklch(0.88 0.028 48)',
    300: 'oklch(0.82 0.042 48)',
    400: 'oklch(0.76 0.08 50)',
    500: 'oklch(0.68 0.12 48)',
    600: 'oklch(0.58 0.135 48)',
    700: 'oklch(0.52 0.14 40)',
  },
  ocre: {
    50: 'oklch(0.96 0.012 60)',
    100: 'oklch(0.92 0.02 60)',
    200: 'oklch(0.88 0.035 62)',
    300: 'oklch(0.82 0.055 62)',
    400: 'oklch(0.75 0.08 60)',
    500: 'oklch(0.68 0.1 58)',
    600: 'oklch(0.58 0.1 58)',
  },
  // Estados de riesgo
  risk: {
    critico: 'oklch(0.62 0.22 25)',      // Rojo-naranja
    alto: 'oklch(0.68 0.15 45)',         // Naranja-terracota
    medio: 'oklch(0.72 0.12 70)',        // Amarillo-ocre
    bajo: 'oklch(0.65 0.13 140)',        // Verde-limón
  },
  // Soft backgrounds
  riskSoft: {
    critico: 'oklch(0.92 0.04 25)',
    alto: 'oklch(0.93 0.035 48)',
    medio: 'oklch(0.94 0.028 70)',
    bajo: 'oklch(0.93 0.035 140)',
  },
  // Accent
  accent: 'oklch(0.72 0.22 145)',        // Verde brillante (status/ping)
  
  // Neutral
  neutral: {
    50: 'oklch(0.98 0.008 75)',
    100: 'oklch(0.96 0.01 75)',
    200: 'oklch(0.92 0.015 75)',
    300: 'oklch(0.88 0.02 75)',
    400: 'oklch(0.75 0.02 70)',
    500: 'oklch(0.62 0.02 65)',
    600: 'oklch(0.52 0.025 60)',
    700: 'oklch(0.4 0.025 55)',
    900: 'oklch(0.2 0.03 50)',
  },
};

// Exportar para Tailwind
export const tailwindColors = {
  brown: TEYVA_COLORS.brown,
  terracotta: TEYVA_COLORS.terracotta,
  ocre: TEYVA_COLORS.ocre,
  risk: TEYVA_COLORS.risk,
  neutral: TEYVA_COLORS.neutral,
};
