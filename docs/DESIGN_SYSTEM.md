# TEYVA · Sistema de Diseño

> Rediseño integral de la UI de TEYVA — plataforma de monitoreo de riesgo de
> deslizamientos en Medellín. Dirección visual cálida y conversacional, inspirada
> en Cleo (meetcleo.com) pero adaptada a un contexto institucional/territorial:
> **profesional pero cercano**.

El prototipo de referencia vive en `Teyva Dashboard.dc.html`.

---

## 1. Principios de diseño

| Principio | Qué significa en TEYVA |
|-----------|------------------------|
| **Cálido, no frío** | Abandonamos el verde/teal corporativo por una paleta tierra (marrón, terracota, ocre, beige). El riesgo se comunica con seriedad, pero la interfaz se siente humana. |
| **Conversacional** | El sistema le habla al usuario en primera persona ("Hoy hay 7 comunas que vale la pena vigilar"). Nada de jerga técnica innecesaria. |
| **Claridad sobre densidad** | Menos números por pantalla, más jerarquía. Cada dato gana su lugar. |
| **Acción a tiempo** | Toda información de riesgo viene acompañada de una recomendación concreta. |

---

## 2. Color

Todos los colores se definen en **OKLCH** para mantener consistencia perceptual
de luminosidad y croma entre tonos.

### 2.1 Tonos base (tierra cálida)

| Token | Valor OKLCH | Uso |
|-------|-------------|-----|
| `--background` | `oklch(0.96 0.014 75)` | Fondo de la app (beige cálido) |
| `--card` | `oklch(0.99 0.008 75)` | Tarjetas, paneles |
| `--foreground` | `oklch(0.26 0.035 45)` | Texto principal (marrón oscuro) |
| `--muted-foreground` | `oklch(0.52 0.035 55)` | Texto secundario |
| `--border` | `oklch(0.90 0.018 70)` | Bordes sutiles |

### 2.2 Marca / Acento (terracota)

| Token | Valor OKLCH | Uso |
|-------|-------------|-----|
| `--accent` | `oklch(0.58 0.14 42)` | Botones primarios, logo, envío de chat |
| `--accent-deep` | `oklch(0.45 0.10 38)` | Fin del degradado del logo |
| `--gold` | `oklch(0.82 0.14 78)` | Detalle decorativo (punto del logo, acentos del hero) |

**Variantes de acento curadas** (disponibles como tweak en el prototipo):
- Terracota — `oklch(0.58 0.14 42)` *(default)*
- Rojo arcilla — `oklch(0.55 0.15 28)`
- Ámbar — `oklch(0.6 0.13 62)`
- Verde musgo — `oklch(0.5 0.11 145)`

### 2.3 Hero (degradado profundo)

```css
/* heroStyle: "deep" (default) */
background: linear-gradient(140deg,
  oklch(0.32 0.06 42) 0%,
  oklch(0.38 0.08 38) 55%,
  oklch(0.34 0.07 30) 100%);

/* heroStyle: "warm" */
background: linear-gradient(140deg,
  var(--accent) 0%,
  oklch(0.5 0.13 45) 55%,
  oklch(0.62 0.13 65) 100%);
```

### 2.4 Escala de riesgo (semáforo cálido)

La pieza más importante del sistema. Cada nivel tiene un color sólido y una
versión "soft" para fondos.

| Nivel | Color | Soft (fondo) | Cuándo |
|-------|-------|--------------|--------|
| **Bajo** | `oklch(0.64 0.11 150)` verde | `oklch(0.95 0.04 150)` | Estable, monitoreo rutinario |
| **Medio** | `oklch(0.78 0.13 80)` ocre | `oklch(0.96 0.05 85)` | Vigilar evolución |
| **Alto** | `oklch(0.66 0.16 50)` naranja | `oklch(0.95 0.05 55)` | Activar protocolos preventivos |
| **Crítico** | `oklch(0.55 0.19 30)` terracota-rojo | `oklch(0.94 0.05 35)` | Alerta máxima, evacuación |

> Nota: los cuatro niveles comparten una croma y luminosidad cercanas para que el
> mapa se lea como una sola familia, no como cuatro colores sueltos.

---

## 3. Tipografía

Dos familias de Google Fonts, ambas con personalidad pero legibles:

| Rol | Fuente | Uso |
|-----|--------|-----|
| **Display** | `Bricolage Grotesque` (700–800) | Títulos, KPIs, números grandes, logo. Cálida y característica. |
| **Texto** | `Hanken Grotesk` (400–700) | Cuerpo, etiquetas, UI. Amigable y muy legible. |

```css
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400..800&family=Hanken+Grotesk:wght@400..700&display=swap');
```

### Escala

| Elemento | Tamaño | Peso | Familia |
|----------|--------|------|---------|
| Hero title | 40px | 700 | Bricolage |
| KPI value | 32px | 700 | Bricolage |
| Card title | 26px | 700 | Bricolage |
| Section title | 15–16px | 700 | Bricolage |
| Body | 14–16px | 400–500 | Hanken |
| Label / eyebrow | 11–12.5px, `letter-spacing: 0.12–0.16em`, uppercase | 600 | Hanken |

> Se eliminó **Inter** (demasiado neutral/genérico) y **Fraunces** del sistema anterior.

---

## 4. Forma y elevación

| Token | Valor | Uso |
|-------|-------|-----|
| Radio tarjetas | `20–24px` | Paneles, KPI cards |
| Radio hero | `28px` | Sección hero |
| Radio botones | `13–14px` | Botones |
| Radio chips/pills | `99px` | Etiquetas de nivel, sugerencias, estado |
| Sombra suave | `0 1px 2px oklch(0.5 0.05 50 / 0.04), 0 10px 26px -16px oklch(0.5 0.06 45 / 0.3)` | Tarjetas |
| Sombra elevada | `0 24px 60px -20px oklch(0.4 0.06 45 / 0.4)` | Chat, modales |

---

## 5. Componentes

### Header
Logo "T" en cuadro redondeado con degradado de marca + punto dorado. Wordmark
TEYVA en Bricolage. Navegación pill, indicador "Sistema en línea" con pulso, y
avatar de usuario.

### Hero conversacional
El corazón del nuevo tono. Saludo en primera persona que resume el estado del
valle + dos tarjetas de glassmorphism con métricas clave (lluvia 24h, comunas en
alerta) + CTAs ("Hablar con Teyva", "Ver comunas en alerta").

### KPI Cards
Cuatro indicadores: nivel general, comunas en alerta, lluvia máxima 24h, eventos
de la semana. Cada uno con ícono en cuadro de color, valor grande en Bricolage y
una línea de tendencia.

### Mapa de riesgo
Panel con fondo de "terreno" y el río Medellín. Marcadores circulares por comuna,
**dimensionados y coloreados por nivel de riesgo** (a mayor riesgo, mayor tamaño y
color más cálido). Click → selección con anillo de resalte. Leyenda flotante.

### Panel de detalle de comuna
Aparece al seleccionar. Muestra nivel (pill de color), barra de índice de riesgo,
lluvia 24h, eventos previos y una **recomendación accionable** según el nivel.

### Gráfico de precipitación
Barras de 7 días, coloreadas por intensidad (verde → ocre → naranja). Se adapta a
la comuna seleccionada.

### Chat widget "Teyva"
Asistente flotante con personalidad. Header de marca, burbujas diferenciadas
(usuario = acento, bot = blanco), chips de sugerencias rápidas y respuestas
contextuales según la comuna o el tema preguntado. Es la máxima expresión del
tono conversacional tipo Cleo.

---

## 6. Tono de voz (copywriting)

| ❌ Antes (institucional seco) | ✅ Ahora (cálido + claro) |
|------------------------------|---------------------------|
| "Monitoreo de riesgo de deslizamientos para Medellín" | "Hoy hay 7 comunas que vale la pena vigilar." |
| "Seleccione una comuna del mapa" | "Toca cualquier marcador y te cuento cómo está." |
| "Nivel de riesgo: ALTO" | "Riesgo alto (68%). Activa protocolos preventivos…" |

**Reglas:**
1. Habla en presente y en primera/segunda persona.
2. Cada dato de riesgo termina en una acción.
3. Sin jerga: "índice de riesgo", no "probabilidad de inferencia del modelo".
4. Emojis con moderación, solo donde aportan calidez (🌦️ 💡 ⚠️).

---

## 7. Cómo llevarlo al código (Next.js / shadcn)

El proyecto usa Tailwind v4 + shadcn con tokens en `globals.css`. Reemplaza el
bloque `:root` por la nueva paleta:

```css
:root {
  --radius: 0.9rem;
  --background: oklch(0.96 0.014 75);
  --foreground: oklch(0.26 0.035 45);
  --card: oklch(0.99 0.008 75);
  --card-foreground: oklch(0.28 0.04 45);
  --primary: oklch(0.58 0.14 42);          /* terracota */
  --primary-foreground: oklch(0.98 0.01 80);
  --secondary: oklch(0.92 0.02 70);
  --muted: oklch(0.94 0.018 72);
  --muted-foreground: oklch(0.52 0.035 55);
  --accent: oklch(0.82 0.14 78);            /* dorado */
  --destructive: oklch(0.55 0.19 30);
  --border: oklch(0.90 0.018 70);
  --input: oklch(0.91 0.02 68);
  --ring: oklch(0.58 0.14 42);
  /* riesgo */
  --risk-bajo: oklch(0.64 0.11 150);
  --risk-medio: oklch(0.78 0.13 80);
  --risk-alto: oklch(0.66 0.16 50);
  --risk-critico: oklch(0.55 0.19 30);
}
```

Y las fuentes en `@theme`:

```css
--font-display: 'Bricolage Grotesque', ui-serif, serif;
--font-sans: 'Hanken Grotesk', ui-sans-serif, system-ui, sans-serif;
```

> Los componentes shadcn existentes (`button`, `card`, `badge`, etc.) heredarán
> automáticamente la nueva paleta. Solo hay que ajustar los componentes de
> dashboard (`header.tsx`, `kpi-cards.tsx`, `teyva-chat.tsx`, etc.) para usar el
> nuevo layout y copy mostrados en el prototipo.

---

## 8. Archivos

- `Teyva Dashboard.dc.html` — prototipo interactivo completo (abre en el navegador).
- `DESIGN_SYSTEM.md` — este documento.

**Tweaks disponibles en el prototipo:** color de marca (4 opciones), estilo del
hero (profundo / cálido) y mostrar/ocultar hero.
