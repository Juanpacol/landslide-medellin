'use client';

import React, { useEffect, useState } from 'react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  LineElement,
  PointElement,
  Title,
  Tooltip,
  Legend,
  BarController,
  LineController,
} from 'chart.js';
import { Chart } from 'react-chartjs-2';
import { fetchChartData, type DailyChartData } from '@/lib/api';

ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  LineElement,
  PointElement,
  Title,
  Tooltip,
  Legend,
  BarController,
  LineController
);

interface RainfallChartProps {
  communeId?: string | null;
}

export function RainfallChart({ communeId }: RainfallChartProps) {
  const [dailyData, setDailyData] = useState<DailyChartData[]>([]);

  useEffect(() => {
    fetchChartData(communeId)
      .then(setDailyData)
      .catch(() => setDailyData([]));
  }, [communeId]);

  const data = {
    labels: dailyData.map((d) => d.date),
    datasets: [
      {
        type: 'bar' as const,
        label: 'Lluvia (mm)',
        data: dailyData.map((d) => d.rainfall),
        backgroundColor: 'oklch(0.66 0.16 50 / 0.65)',
        borderColor: 'oklch(0.66 0.16 50)',
        borderWidth: 1,
        borderRadius: 6,
        yAxisID: 'y',
        order: 2,
      },
      {
        type: 'line' as const,
        label: 'Deslizamientos',
        data: dailyData.map((d) => d.landslides),
        borderColor: 'oklch(0.55 0.19 30)',
        backgroundColor: 'oklch(0.55 0.19 30 / 0.15)',
        borderWidth: 2,
        pointRadius: 3,
        pointBackgroundColor: 'oklch(0.55 0.19 30)',
        yAxisID: 'y1',
        tension: 0.3,
        order: 1,
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index' as const, intersect: false },
    plugins: {
      legend: {
        position: 'top' as const,
        labels: { color: 'oklch(0.52 0.035 55)', usePointStyle: true, padding: 16 },
      },
      title: {
        display: true,
        text: communeId ? `Precipitación · ${communeId}` : 'Precipitación · 7 días',
        color: 'oklch(0.3 0.04 45)',
        font: { size: 13, weight: 'bold' as const, family: 'Bricolage Grotesque' },
        padding: { bottom: 12 },
      },
      tooltip: {
        backgroundColor: 'oklch(0.99 0.008 75)',
        titleColor: 'oklch(0.28 0.04 45)',
        bodyColor: 'oklch(0.52 0.035 55)',
        borderColor: 'oklch(0.90 0.018 70)',
        borderWidth: 1,
        padding: 10,
      },
    },
    scales: {
      x: {
        grid: { color: 'oklch(0.90 0.018 70 / 0.5)' },
        ticks: { color: 'oklch(0.52 0.035 55)', maxRotation: 45, minRotation: 45, font: { size: 10 } },
      },
      y: {
        type: 'linear' as const,
        position: 'left' as const,
        title: { display: true, text: 'Lluvia (mm)', color: 'oklch(0.66 0.16 50)', font: { size: 11, weight: 'bold' as const } },
        grid: { color: 'oklch(0.90 0.018 70 / 0.5)' },
        ticks: { color: 'oklch(0.52 0.035 55)' },
      },
      y1: {
        type: 'linear' as const,
        position: 'right' as const,
        title: { display: true, text: 'Deslizamientos', color: 'oklch(0.55 0.19 30)', font: { size: 11, weight: 'bold' as const } },
        grid: { drawOnChartArea: false },
        ticks: { color: 'oklch(0.55 0.19 30)', stepSize: 1 },
      },
    },
  };

  const cardStyle: React.CSSProperties = {
    height: '100%',
    borderRadius: '24px',
    border: '1px solid oklch(0.9 0.018 70)',
    background: 'oklch(0.99 0.008 75)',
    padding: '20px',
    boxShadow: '0 1px 2px oklch(0.5 0.05 50 / 0.04), 0 14px 36px -22px oklch(0.5 0.06 45 / 0.3)',
  };

  if (dailyData.length === 0) {
    return (
      <div style={{ ...cardStyle, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <span style={{ fontSize: '13.5px', color: 'oklch(0.55 0.035 55)' }}>Sin datos de precipitación por ahora</span>
      </div>
    );
  }

  return (
    <div style={cardStyle}>
      <div style={{ height: '100%' }}>
        <Chart type="bar" data={data} options={options} />
      </div>
    </div>
  );
}
