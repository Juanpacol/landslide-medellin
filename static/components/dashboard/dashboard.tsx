'use client';

import { useEffect, useState } from 'react';
import { Header } from './header';
import { KpiCards } from './kpi-cards';
import { MedellinMap } from './medellin-map';
import { CommuneInfo } from './commune-info';
import { RainfallChart } from './rainfall-chart';
import { TeyvaChatWidget } from './teyva-chat';
import { fetchCommuneDetail, type CommuneDetail, type CommuneFeature } from '@/lib/api';

type CommuneProps = CommuneFeature['properties'];

export function Dashboard() {
  const [selectedCommune, setSelectedCommune] = useState<CommuneProps | null>(null);
  const [communeDetail, setCommuneDetail] = useState<CommuneDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const chartCommuneId =
    selectedCommune?.parent_commune_id && /^\d+$/.test(selectedCommune.parent_commune_id)
      ? selectedCommune.parent_commune_id
      : null;

  useEffect(() => {
    if (!chartCommuneId) {
      setCommuneDetail(null);
      return;
    }
    setDetailLoading(true);
    fetchCommuneDetail(chartCommuneId)
      .then((data) => setCommuneDetail(data))
      .catch(() => setCommuneDetail(null))
      .finally(() => setDetailLoading(false));
  }, [chartCommuneId]);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <Header />

      <main className="mx-auto max-w-[1600px] space-y-5 px-6 py-6">
        <section className="relative overflow-hidden rounded-3xl border border-border/60 bg-[image:var(--gradient-hero)] p-6 text-white shadow-[var(--shadow-soft)] md:p-8">
          <div
            aria-hidden
            className="absolute inset-0 opacity-30"
            style={{
              backgroundImage:
                'radial-gradient(circle at 20% 80%, rgba(255,255,255,0.15), transparent 40%), radial-gradient(circle at 80% 20%, rgba(242,201,76,0.25), transparent 40%)',
            }}
          />
          <div className="relative max-w-2xl">
            <div className="text-[11px] uppercase tracking-[0.22em] text-white/70">Plataforma TEYVA · Antioquia</div>
            <h2 className="mt-2 font-display text-3xl font-semibold leading-tight tracking-tight md:text-4xl">
              Monitoreo de riesgo de deslizamientos para Medellin
            </h2>
            <p className="mt-2 max-w-xl text-sm text-white/80 md:text-base">
              Datos geoespaciales, precipitacion y alertas en tiempo real para proteger las laderas y las comunidades del
              valle.
            </p>
          </div>
        </section>

        <KpiCards />

        <section className="grid gap-5 xl:grid-cols-[1fr_420px]">
          <div className="h-[640px]">
            <MedellinMap
              onCommuneSelect={setSelectedCommune}
              selectedCommuneId={selectedCommune?.commune_id ?? null}
            />
          </div>

          <div className="space-y-5">
            <div className="h-[390px]">
              <CommuneInfo commune={selectedCommune} detail={communeDetail} loading={detailLoading} />
            </div>
            <div className="h-[225px]">
              <RainfallChart communeId={chartCommuneId} />
            </div>
          </div>
        </section>

        <footer className="pt-6 pb-10 text-center text-xs text-muted-foreground">
          TEYVA · Sistema institucional de analisis de riesgo · Medellin, Antioquia
        </footer>
      </main>

      <TeyvaChatWidget selectedCommune={selectedCommune} />
    </div>
  );
}
