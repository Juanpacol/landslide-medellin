# 📦 TEYVA · Frontend Handoff para Cursor

**Proyecto:** TEYVA — Sistema de análisis de riesgo de deslizamientos
**Cobertura:** Medellín (16 comunas / ~269 barrios) + Bello (~132 barrios) → **401 polígonos**
**Stack frontend:** TanStack Start v1 + React 19 + Vite 7 + Tailwind v4 + Leaflet + shadcn/ui
**Backend objetivo (Cursor):** FastAPI ya existente (no incluido aquí)

---

## 1. Objetivo de este documento

Entregar a Cursor **todo lo necesario** para integrar el frontend TEYVA con el backend FastAPI:

1. Arquitectura de pantallas y layout
2. Sistema de diseño (tokens, tipografía, paleta)
3. Componentes React listos
4. Contratos de API esperados (FastAPI ↔ frontend)
5. Plan de migración de datos mock → datos reales

---

## 2. Estructura del proyecto

```
src/
├── routes/
│   ├── __root.tsx              # Shell HTML, ThemeProvider, head/meta SEO
│   └── index.tsx               # Dashboard (Hero + KPIs + Mapa + Detalle + Chat)
├── components/
│   └── teyva/
│       ├── Header.tsx          # Logo, status, theme toggle
│       ├── KpiCards.tsx        # 6 tarjetas resumen ejecutivo
│       ├── RiskMap.tsx         # Mapa Leaflet + GeoJSON barrios + filtros
│       ├── ComunaDetail.tsx    # Panel lateral con detalle del barrio/comuna
│       ├── ChatWidget.tsx      # Asistente IA flotante (FastAPI /api/chat)
│       └── ThemeProvider.tsx   # next-themes (light/dark)
├── lib/
│   ├── teyva-data.ts           # Tipos Comuna, RiskLevel, RISK_COLORS, mock 16 comunas
│   ├── barrios-data.ts         # Tipos Barrio, derivación desde GeoJSON, adaptador
│   ├── barrios-medellin.json   # GeoJSON 401 barrios (Medellín + Bello, ~772KB)
│   └── comunas-medellin.json   # GeoJSON respaldo a nivel comuna
└── styles.css                  # Design tokens (oklch), gradientes, leaflet overrides
```

---

## 3. Sistema de diseño TEYVA

### 3.1 Identidad
- **Estética:** ecofriendly antioqueño · montañas, hojas, silleteros, tierra, agua
- **Tono:** institucional, moderno, profesional, cálido

### 3.2 Tipografía
- **Display:** `Fraunces` (serif moderna, títulos)
- **Body:** `Inter` (sans, UI)

### 3.3 Paleta semántica (definida en `styles.css` con `oklch`)

| Token | Valor (hex aprox) | Uso |
|---|---|---|
| `--forest` | `#1F6F50` | Verde bosque (primary) |
| `--leaf`   | `#5FA777` | Verde hoja |
| `--earth`  | `#8C5A3C` | Tierra |
| `--floral` | `#E67E22` | Naranja silletero |
| `--sun`    | `#F2C94C` | Acento solar |
| `--river`  | `#2D9CDB` | Azul río |
| `--risk-low`      | verde   | Riesgo Bajo |
| `--risk-medium`   | amarillo| Riesgo Medio |
| `--risk-high`     | naranja | Riesgo Alto |
| `--risk-critical` | rojo    | Riesgo Crítico |

### 3.4 Gradientes y sombras
- `--gradient-hero`: verde→azul para hero del dashboard
- `--gradient-leaf`: verde hoja→bosque para botones premium
- `--shadow-soft` y `--shadow-elevated`: sombras suaves teñidas en verde

### 3.5 Modo oscuro
- Toggle global con `next-themes` (atributo `class="dark"`)
- Tiles del mapa se ajustan vía CSS filters (ver `styles.css` línea ~213)

---

## 4. Arquitectura de pantallas (v1)

### Vista única: `/` (Dashboard)

```
┌─────────────────────────────────────────────────────────┐
│  HEADER  [logo TEYVA]  [estado · hora]  [☾/☀]          │
├─────────────────────────────────────────────────────────┤
│  HERO (gradient-hero)                                   │
│  "Monitoreo de riesgo de deslizamientos para Medellín" │
├─────────────────────────────────────────────────────────┤
│  KPIs (6 tarjetas)                                      │
│  Comunas | Crítico | Alto | Eventos | Tendencia | QoD  │
├──────────────────────────────────┬──────────────────────┤
│  RISK MAP (Leaflet + GeoJSON)    │  COMUNA DETAIL       │
│  - Filtros por nivel             │  - Score %           │
│  - Toggle "ladera"               │  - Métricas (lluvia) │
│  - Tooltip por barrio            │  - Explicación XAI   │
│  - 401 polígonos clickeables     │  - Versión modelo    │
├──────────────────────────────────┴──────────────────────┤
│  FOOTER institucional                                   │
└─────────────────────────────────────────────────────────┘
                                      ┌──── ChatWidget ───┐
                                      │  TEYVA Assistant  │
                                      │ (POST /api/chat)  │
                                      └───────────────────┘
```

### Navegación futura (sugerida)
- `/` Dashboard (actual)
- `/comuna/$id` Detalle profundo + serie temporal `daily_data`
- `/alertas` Listado de alertas activas (`/api/risk/alerts`)
- `/predicciones` Últimas corridas (`/api/risk/predictions/latest`)
- `/scraper` Estado de pipeline (`/api/scraper/status`, `/logs`)

---

## 5. Contratos de API (FastAPI ↔ Frontend)

> El frontend espera estas rutas bajo `/api`. Configurar proxy de Vite o reverse-proxy en producción.

### 5.1 Comunas

**`GET /api/comunas`**
```json
[
  {
    "id": 1,
    "name": "Popular",
    "nickname": "Comuna 1",
    "riskLevel": "Crítico",   // "Bajo" | "Medio" | "Alto" | "Crítico"
    "riskScore": 0.91,         // 0..1
    "events": 24,
    "hillside": true,
    "rain7d": 142,             // mm
    "rain30d": 410,            // mm
    "trend": 18,               // % vs semana anterior
    "lastPrediction": "Hace 12 min",
    "modelVersion": "teyva-risk v2.4.1",
    "explanation": "…",
    "center": [-75.546, 6.295] // [lng, lat]
  }
]
```

**`GET /api/comuna/{id}`** → mismo objeto + `daily_data: [{date, rain, riskScore, events}]`

### 5.2 Barrios (recomendado para v1.1)

**`GET /api/barrios`** → lista de `Barrio` (ver `barrios-data.ts`)
**`GET /api/barrios/{codigo}`** → detalle + serie temporal

Ahora mismo `barrios-data.ts` sintetiza los valores a partir de la comuna; cuando el backend tenga riesgo por barrio, **reemplazar `buildBarrio()` por una llamada `fetch('/api/barrios')`** y mantener el adaptador `barrioAsComuna()`.

### 5.3 Alertas

**`GET /api/risk/alerts`**
```json
[
  { "id": "alt_xx", "barrioId": "0101", "level": "Crítico",
    "message": "Saturación crítica en ladera",
    "createdAt": "2026-04-26T15:30:00Z", "active": true }
]
```

### 5.4 Predicciones

**`GET /api/risk/predictions/latest`** → metadata del modelo + run_id + timestamp.

### 5.5 Chat (ya implementado en `ChatWidget.tsx`)

**`POST /api/chat`**
```json
// Request
{
  "session_id": "sess_xxx",
  "message": "¿Por qué subió el riesgo en Popular?",
  "context": {
    "selected_comuna_id": 1,
    "selected_comuna_name": "Popular",
    "risk_level": "Crítico"
  }
}
// Response
{ "reply": "El riesgo subió porque…" }
// (también acepta { "answer": "…" } como fallback)
```

**`GET /api/chat/history/{session_id}`**
```json
{
  "messages": [
    { "id": "m1", "role": "user", "content": "...", "ts": 1714000000000 },
    { "id": "m2", "role": "assistant", "content": "...", "ts": 1714000001000 }
  ]
}
```
- `session_id` se genera y persiste en `localStorage` (`teyva_session_id`)
- Estado de envío, errores y reintento ya gestionados
- Sugerencias rápidas contextuales según barrio seleccionado

### 5.6 Scraper

- `GET /api/scraper/status` → `{ running, lastRun, nextRun, source }`
- `GET /api/scraper/logs?limit=100` → `[{ ts, level, message }]`

---

## 6. Plan de integración para Cursor

### Paso 1 · Variables de entorno
Crear `.env`:
```
VITE_API_BASE=/api
```
Y en `ChatWidget.tsx` reemplazar `const API_BASE = "/api"` por `import.meta.env.VITE_API_BASE`.

### Paso 2 · Proxy Vite (desarrollo)
En `vite.config.ts` agregar:
```ts
server: {
  proxy: {
    "/api": { target: "http://localhost:8000", changeOrigin: true }
  }
}
```

### Paso 3 · Reemplazar mocks por TanStack Query
Crear `src/lib/api.ts`:
```ts
import { useQuery } from "@tanstack/react-query";
const base = import.meta.env.VITE_API_BASE ?? "/api";

export const useComunas = () =>
  useQuery({
    queryKey: ["comunas"],
    queryFn: () => fetch(`${base}/comunas`).then(r => r.json()),
    refetchInterval: 60_000,
  });

export const useAlerts = () =>
  useQuery({
    queryKey: ["alerts"],
    queryFn: () => fetch(`${base}/risk/alerts`).then(r => r.json()),
    refetchInterval: 30_000,
  });
```

Sustituir `import { COMUNAS } from "@/lib/teyva-data"` en `KpiCards.tsx` y `barrios-data.ts` por `useComunas()`.

### Paso 4 · Habilitar QueryClient
Ya hay `@tanstack/react-query` instalado. Seguir el patrón obligatorio de TanStack Start en `__root.tsx` y `router.tsx` (ver instrucciones del framework).

### Paso 5 · Producción
Configurar reverse-proxy (nginx / Cloudflare) para enrutar `/api/*` al FastAPI.

---

## 7. Componentes incluidos en este paquete

| Archivo | Descripción |
|---|---|
| `route-root.tsx` | Shell raíz con SEO, ThemeProvider |
| `route-index.tsx` | Dashboard principal |
| `Header.tsx` | Encabezado con toggle tema |
| `KpiCards.tsx` | Resumen ejecutivo (6 KPIs) |
| `RiskMap.tsx` | Mapa Leaflet + filtros + leyenda |
| `ComunaDetail.tsx` | Panel lateral con XAI |
| `ChatWidget.tsx` | Chat IA conectado a FastAPI |
| `ThemeProvider.tsx` | Wrapper next-themes |
| `teyva-data.ts` | Tipos + mock comunas |
| `barrios-data.ts` | Lógica de barrios + adaptador |
| `barrios-medellin.json` | GeoJSON 401 barrios |
| `styles.css` | Design tokens completos |
| `package.json` | Dependencias del proyecto |

---

## 8. Dependencias clave

```
react@19, react-dom@19
@tanstack/react-router@1.168, @tanstack/react-start@1.167
@tanstack/react-query@5.83
react-leaflet@5, leaflet@1.9
tailwindcss@4.2, @tailwindcss/vite@4.2
next-themes@0.4
lucide-react@0.575
shadcn/ui (Radix primitives instalados)
```

Instalar con: `bun install` o `npm install`.

---

## 9. Checklist para Cursor

- [ ] Copiar `barrios-medellin.json` a `src/lib/`
- [ ] Crear `.env` con `VITE_API_BASE`
- [ ] Configurar proxy Vite hacia FastAPI
- [ ] Implementar endpoints listados en sección 5
- [ ] Reemplazar `COMUNAS` mock por `useQuery` desde `/api/comunas`
- [ ] Migrar `barrios-data.ts` a fetch desde `/api/barrios` cuando exista
- [ ] Verificar contrato `/api/chat` y `/api/chat/history/{session_id}`
- [ ] Probar light/dark mode
- [ ] Verificar SSR del shell (TanStack Start) sin romper Leaflet (ya cargado con `lazy`)

---

**Generado para handoff TEYVA · 2026-04-26**
