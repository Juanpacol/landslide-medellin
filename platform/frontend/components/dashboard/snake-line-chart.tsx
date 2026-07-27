'use client';

import { useEffect, useState } from 'react';
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Line,
  ComposedChart,
} from 'recharts';
import { fetchSnakeLine, type SnakeLineData } from '@/lib/api';

const STATUS_COLOR: Record<string, string> = {
  VERDE: 'oklch(0.65 0.15 150)',
  AMARILLO: 'oklch(0.72 0.14 85)',
  ROJO: 'oklch(0.58 0.22 25)',
};

interface SnakeLineChartProps {
  communeId: string;
}

export function SnakeLineChart({ communeId }: SnakeLineChartProps) {
  const [data, setData] = useState<SnakeLineData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchSnakeLine(communeId)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch(() => {
        if (!cancelled) setData(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [communeId]);

  if (loading) return <div className="text-center py-6 text-sm text-muted-foreground">Cargando Snake Line…</div>;
  if (!data) return <div className="text-center py-6 text-sm text-muted-foreground">Sin datos suficientes.</div>;

  const { slope, intercept } = data.critical_line;
  const linePoints = [
    { x: 0, criticalY: intercept },
    { x: 100, criticalY: Math.max(0, slope * 100 + intercept) },
  ];

  const historyPoints = data.history.map((p) => ({ ...p, fill: STATUS_COLOR[p.status] }));

  return (
    <div className="w-full">
      <div className="flex items-center gap-3 mb-3">
        <span
          className="inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-bold"
          style={{ background: `${STATUS_COLOR[data.status]}22`, color: STATUS_COLOR[data.status] }}
        >
          <span className="h-2 w-2 rounded-full" style={{ background: STATUS_COLOR[data.status] }} />
          {data.status}
        </span>
        <span className="text-xs text-muted-foreground">
          SWI actual: {data.x.toFixed(0)}% · Lluvia 60min: {data.y.toFixed(1)} mm
        </span>
      </div>

      <div className="w-full h-80">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={linePoints} margin={{ top: 10, right: 20, bottom: 10, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
            <XAxis
              dataKey="x"
              type="number"
              domain={[0, 100]}
              label={{ value: 'SWI — Saturación del suelo (%)', position: 'insideBottom', offset: -5, fontSize: 11 }}
              stroke="var(--muted-foreground)"
            />
            <YAxis
              type="number"
              domain={[0, 'dataMax + 10']}
              label={{ value: 'Lluvia últimos 60 min (mm)', angle: -90, position: 'insideLeft', fontSize: 11 }}
              stroke="var(--muted-foreground)"
            />
            <Tooltip
              contentStyle={{ backgroundColor: 'var(--card)', border: '1px solid var(--border)', borderRadius: '8px' }}
            />
            <Line
              type="linear"
              dataKey="criticalY"
              stroke="oklch(0.58 0.22 25)"
              strokeWidth={2}
              strokeDasharray="6 4"
              dot={false}
              name="Línea crítica"
              isAnimationActive={false}
            />
            <Scatter data={historyPoints} dataKey="y" name="Historial 48h">
              {historyPoints.map((p, i) => (
                <circle key={i} r={3} fill={p.fill} />
              ))}
            </Scatter>
            <Scatter
              data={[{ x: data.x, y: data.y }]}
              dataKey="y"
              name="Ahora"
              shape={(props: { cx?: number; cy?: number }) => (
                <circle cx={props.cx} cy={props.cy} r={7} fill={STATUS_COLOR[data.status]} stroke="white" strokeWidth={2} />
              )}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <p className="text-[11px] text-muted-foreground mt-2">
        MVP: línea crítica conservadora (sin calibrar con eventos históricos reales todavía). Punto grande = estado actual.
      </p>
    </div>
  );
}
