'use client';

import { useEffect, useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { Activity } from 'lucide-react';

interface SeismicChartData {
  date: string;
  magnitude: number;
  count: number;
}

export function SeismicChart() {
  const [data, setData] = useState<SeismicChartData[]>([]);
  const [loading, setLoading] = useState(true);
  const [staleInfo, setStaleInfo] = useState<{ isStale: boolean; daysSinceLast: number | null }>({
    isStale: false,
    daysSinceLast: null,
  });

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch('/api/risk/seismic-events?days=30');
        if (!res.ok) throw new Error();
        const json = await res.json();

        setStaleInfo({ isStale: !!json.is_stale, daysSinceLast: json.days_since_last_event ?? null });

        const byDay: Record<string, { count: number; maxMag: number }> = {};
        (json.events || []).forEach((e: any) => {
          const day = e.event_local_at?.substring(0, 10) || 'unknown';
          if (!byDay[day]) byDay[day] = { count: 0, maxMag: 0 };
          byDay[day].count += 1;
          byDay[day].maxMag = Math.max(byDay[day].maxMag, e.magnitude || 0);
        });

        const chartData = Object.entries(byDay)
          .map(([date, { count, maxMag }]) => ({
            date,
            magnitude: parseFloat(maxMag.toFixed(1)),
            count,
          }))
          .sort((a, b) => a.date.localeCompare(b.date));

        setData(chartData);
      } catch {
        setData([]);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) return <div className="text-center py-4 text-sm text-muted-foreground">Cargando sismos…</div>;

  const staleBanner = staleInfo.isStale && (
    <div
      className="mb-3 rounded-lg px-3 py-2 text-xs"
      style={{ background: 'oklch(0.94 0.05 75)', color: 'oklch(0.5 0.1 60)' }}
    >
      ⚠ El feed sísmico lleva {staleInfo.daysSinceLast ?? '?'} días sin eventos nuevos — puede
      indicar una fuente caída, no necesariamente ausencia de sismos.
    </div>
  );

  if (!data.length) {
    return (
      <div className="flex flex-col items-center py-8 text-muted-foreground">
        {staleBanner}
        <div className="flex flex-col items-center justify-center">
          <Activity className="w-6 h-6 mb-2 opacity-50" />
          <p className="text-sm">
            {staleInfo.isStale ? 'Sin datos recientes del feed sísmico' : 'Sin sismos registrados en 30 días'}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full">
      {staleBanner}
      <div className="h-80">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 11 }}
            angle={-45}
            textAnchor="end"
            height={60}
            stroke="var(--muted-foreground)"
          />
          <YAxis stroke="var(--muted-foreground)" />
          <Tooltip
            contentStyle={{
              backgroundColor: 'var(--card)',
              border: '1px solid var(--border)',
              borderRadius: '8px',
              color: 'var(--foreground)',
            }}
            formatter={(value) => {
              if (typeof value === 'number') {
                return value.toFixed(1);
              }
              return value;
            }}
          />
          <Legend />
          <Bar
            dataKey="magnitude"
            fill="var(--primary)"
            name="Magnitud máxima (M)"
            radius={[8, 8, 0, 0]}
          />
          <Bar
            dataKey="count"
            fill="var(--muted)"
            name="# Sismos"
            radius={[8, 8, 0, 0]}
          />
        </BarChart>
      </ResponsiveContainer>
      </div>
    </div>
  );
}
