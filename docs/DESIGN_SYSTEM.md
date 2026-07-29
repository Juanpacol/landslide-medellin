# TEYVA · Design System

> Full UI redesign for TEYVA — Medellín landslide risk monitoring platform. Warm,
> conversational visual direction, inspired by Cleo (meetcleo.com) but adapted to an
> institutional/territorial context: **professional but approachable**.

Reference prototype lives in `Teyva Dashboard.dc.html`.

---

## 1. Design principles

| Principle | What it means in TEYVA |
|-----------|------------------------|
| **Warm, not cold** | We drop the corporate green/teal for an earth palette (brown, terracotta, ochre, beige). Risk is communicated with seriousness, but the interface feels human. |
| **Conversational** | The system speaks to the user in first person ("Hoy hay 7 comunas que vale la pena vigilar"). No unnecessary technical jargon. |
| **Clarity over density** | Fewer numbers per screen, more hierarchy. Every data point earns its place. |
| **Timely action** | Every piece of risk information comes with a concrete recommendation. |

---

## 2. Color

All colors are defined in **OKLCH** to keep perceptual lightness/chroma consistent across tones.

### 2.1 Base tones (warm earth)

| Token | OKLCH value | Use |
|-------|-------------|-----|
| `--background` | `oklch(0.96 0.014 75)` | App background (warm beige) |
| `--card` | `oklch(0.99 0.008 75)` | Cards, panels |
| `--foreground` | `oklch(0.26 0.035 45)` | Primary text (dark brown) |
| `--muted-foreground` | `oklch(0.52 0.035 55)` | Secondary text |
| `--border` | `oklch(0.90 0.018 70)` | Subtle borders |

### 2.2 Brand / Accent (terracotta)

| Token | OKLCH value | Use |
|-------|-------------|-----|
| `--accent` | `oklch(0.58 0.14 42)` | Primary buttons, logo, chat send |
| `--accent-deep` | `oklch(0.45 0.10 38)` | End of the logo gradient |
| `--gold` | `oklch(0.82 0.14 78)` | Decorative detail (logo dot, hero accents) |

**Curated accent variants** (available as a tweak in the prototype):
- Terracotta — `oklch(0.58 0.14 42)` *(default)*
- Clay red — `oklch(0.55 0.15 28)`
- Amber — `oklch(0.6 0.13 62)`
- Moss green — `oklch(0.5 0.11 145)`

### 2.3 Hero (deep gradient)

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

### 2.4 Risk scale (warm traffic light)

The most important piece of the system. Each level has a solid color and a "soft" background
version.

| Level | Color | Soft (background) | When |
|-------|-------|--------------|--------|
| **Low** | `oklch(0.64 0.11 150)` green | `oklch(0.95 0.04 150)` | Stable, routine monitoring |
| **Medium** | `oklch(0.78 0.13 80)` ochre | `oklch(0.96 0.05 85)` | Watch evolution |
| **High** | `oklch(0.66 0.16 50)` orange | `oklch(0.95 0.05 55)` | Activate preventive protocols |
| **Critical** | `oklch(0.55 0.19 30)` terracotta-red | `oklch(0.94 0.05 35)` | Maximum alert, evacuation |

> Note: the four levels share close chroma/lightness so the map reads as one family, not four
> unrelated colors.

---

## 3. Typography

Two Google Fonts families, both with personality but legible:

| Role | Font | Use |
|-----|--------|-----|
| **Display** | `Bricolage Grotesque` (700–800) | Titles, KPIs, large numbers, logo. Warm and distinctive. |
| **Text** | `Hanken Grotesk` (400–700) | Body, labels, UI. Friendly and highly legible. |

```css
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400..800&family=Hanken+Grotesk:wght@400..700&display=swap');
```

### Scale

| Element | Size | Weight | Family |
|----------|--------|------|---------|
| Hero title | 40px | 700 | Bricolage |
| KPI value | 32px | 700 | Bricolage |
| Card title | 26px | 700 | Bricolage |
| Section title | 15–16px | 700 | Bricolage |
| Body | 14–16px | 400–500 | Hanken |
| Label / eyebrow | 11–12.5px, `letter-spacing: 0.12–0.16em`, uppercase | 600 | Hanken |

> **Inter** (too neutral/generic) and **Fraunces** were removed from the previous system.

---

## 4. Shape and elevation

| Token | Value | Use |
|-------|-------|-----|
| Card radius | `20–24px` | Panels, KPI cards |
| Hero radius | `28px` | Hero section |
| Button radius | `13–14px` | Buttons |
| Chip/pill radius | `99px` | Level labels, suggestions, status |
| Soft shadow | `0 1px 2px oklch(0.5 0.05 50 / 0.04), 0 10px 26px -16px oklch(0.5 0.06 45 / 0.3)` | Cards |
| Elevated shadow | `0 24px 60px -20px oklch(0.4 0.06 45 / 0.4)` | Chat, modals |

---

## 5. Components

### Header
"T" logo in a rounded square with a brand gradient + gold dot. TEYVA wordmark in Bricolage.
Pill navigation, pulsing "System online" indicator, and user avatar.

### Conversational hero
The heart of the new tone. First-person greeting summarizing the valley's status + two
glassmorphism cards with key metrics (24h rain, communes on alert) + CTAs ("Talk to Teyva",
"View communes on alert" — Spanish product copy: "Hablar con Teyva", "Ver comunas en alerta").

### KPI Cards
Four indicators: overall level, communes on alert, max 24h rainfall, events this week. Each with
a colored icon square, a large Bricolage value and a trend line.

### Risk map
Panel with a "terrain" background and the Medellín river. Circular markers per commune,
**sized and colored by risk level** (higher risk = larger and warmer color). Click → selection
with a highlight ring. Floating legend.

### Commune detail panel
Appears on selection. Shows level (colored pill), risk index bar, 24h rainfall, prior events and
an **actionable recommendation** for that level.

### Rainfall chart
7-day bars, colored by intensity (green → ochre → orange). Adapts to the selected commune.

### "Teyva" chat widget
Floating assistant with personality. Branded header, differentiated bubbles (user = accent,
bot = white), quick-suggestion chips and contextual replies based on the commune or topic asked
about. The fullest expression of the Cleo-style conversational tone.

---

## 6. Voice and tone (copywriting)

User-facing copy is Spanish (see `CLAUDE.md`'s language rule) — these are the actual product
strings, kept verbatim:

| ❌ Before (dry, institutional) | ✅ Now (warm + clear) |
|------------------------------|---------------------------|
| "Monitoreo de riesgo de deslizamientos para Medellín" | "Hoy hay 7 comunas que vale la pena vigilar." |
| "Seleccione una comuna del mapa" | "Toca cualquier marcador y te cuento cómo está." |
| "Nivel de riesgo: ALTO" | "Riesgo alto (68%). Activa protocolos preventivos…" |

**Rules:**
1. Speak in present tense, first/second person.
2. Every risk data point ends in an action.
3. No jargon: "índice de riesgo", not "probabilidad de inferencia del modelo".
4. Emojis sparingly, only where they add warmth (🌦️ 💡 ⚠️).

---

## 7. Bringing it into code (Next.js / shadcn)

The project uses Tailwind v4 + shadcn with tokens in `globals.css`. Replace the `:root` block
with the new palette:

```css
:root {
  --radius: 0.9rem;
  --background: oklch(0.96 0.014 75);
  --foreground: oklch(0.26 0.035 45);
  --card: oklch(0.99 0.008 75);
  --card-foreground: oklch(0.28 0.04 45);
  --primary: oklch(0.58 0.14 42);          /* terracotta */
  --primary-foreground: oklch(0.98 0.01 80);
  --secondary: oklch(0.92 0.02 70);
  --muted: oklch(0.94 0.018 72);
  --muted-foreground: oklch(0.52 0.035 55);
  --accent: oklch(0.82 0.14 78);            /* gold */
  --destructive: oklch(0.55 0.19 30);
  --border: oklch(0.90 0.018 70);
  --input: oklch(0.91 0.02 68);
  --ring: oklch(0.58 0.14 42);
  /* risk */
  --risk-bajo: oklch(0.64 0.11 150);
  --risk-medio: oklch(0.78 0.13 80);
  --risk-alto: oklch(0.66 0.16 50);
  --risk-critico: oklch(0.55 0.19 30);
}
```

And the fonts in `@theme`:

```css
--font-display: 'Bricolage Grotesque', ui-serif, serif;
--font-sans: 'Hanken Grotesk', ui-sans-serif, system-ui, sans-serif;
```

> Existing shadcn components (`button`, `card`, `badge`, etc.) will automatically inherit the
> new palette. Only the dashboard components (`header.tsx`, `kpi-cards.tsx`, `teyva-chat.tsx`,
> etc.) need adjusting for the new layout and copy shown in the prototype.

---

## 8. Files

- `Teyva Dashboard.dc.html` — full interactive prototype (opens in the browser).
- `DESIGN_SYSTEM.md` — this document.

**Tweaks available in the prototype:** brand color (4 options), hero style (deep / warm) and
show/hide hero.
