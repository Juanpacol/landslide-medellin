import { createFileRoute } from "@tanstack/react-router";
import { lazy, Suspense, useEffect, useState } from "react";
import { Header } from "@/components/teyva/Header";
import { KpiCards } from "@/components/teyva/KpiCards";
import { ComunaDetail } from "@/components/teyva/ComunaDetail";
import { ChatWidget } from "@/components/teyva/ChatWidget";
import type { Comuna } from "@/lib/teyva-data";

// Leaflet usa window — cargar solo en cliente
const RiskMap = lazy(() =>
  import("@/components/teyva/RiskMap").then((m) => ({ default: m.RiskMap })),
);

export const Route = createFileRoute("/")({
  component: Dashboard,
});

function Dashboard() {
  const [selected, setSelected] = useState<Comuna | null>(null);
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <Header />

      <main className="mx-auto max-w-[1600px] space-y-5 px-6 py-6">
        {/* Hero introductorio */}
        <section className="relative overflow-hidden rounded-3xl border border-border/60 bg-[image:var(--gradient-hero)] p-6 text-white shadow-[var(--shadow-soft)] md:p-8">
          <div
            aria-hidden
            className="absolute inset-0 opacity-30"
            style={{
              backgroundImage:
                "radial-gradient(circle at 20% 80%, rgba(255,255,255,0.15), transparent 40%), radial-gradient(circle at 80% 20%, rgba(242,201,76,0.25), transparent 40%)",
            }}
          />
          <div className="relative max-w-2xl">
            <div className="text-[11px] uppercase tracking-[0.22em] text-white/70">
              Plataforma TEYVA · Antioquia
            </div>
            <h2 className="mt-2 font-display text-3xl font-700 leading-tight tracking-tight md:text-4xl">
              Monitoreo de riesgo de deslizamientos para Medellín
            </h2>
            <p className="mt-2 max-w-xl text-sm text-white/80 md:text-base">
              Datos geoespaciales, precipitación y alertas en tiempo real para
              proteger las laderas y las comunidades del valle.
            </p>
          </div>
        </section>

        {/* KPIs */}
        <KpiCards />

        {/* Mapa + detalle */}
        <section className="grid gap-5 lg:grid-cols-[1fr_400px]">
          <div className="h-[640px]">
            {mounted ? (
              <Suspense
                fallback={
                  <div className="h-full animate-pulse rounded-3xl border border-border/60 bg-muted" />
                }
              >
                <RiskMap
                  selectedId={selected?.id ?? null}
                  onSelect={setSelected}
                />
              </Suspense>
            ) : (
              <div className="h-full animate-pulse rounded-3xl border border-border/60 bg-muted" />
            )}
          </div>
          <div className="h-[640px]">
            <ComunaDetail comuna={selected} />
          </div>
        </section>

        <footer className="pt-6 pb-10 text-center text-xs text-muted-foreground">
          TEYVA · Sistema institucional de análisis de riesgo · Medellín, Antioquia
        </footer>
      </main>

      <ChatWidget selected={selected} />
    </div>
  );
}
