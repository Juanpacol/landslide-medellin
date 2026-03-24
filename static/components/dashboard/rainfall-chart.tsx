'use client';

import { useEffect, useState } from 'react';
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
} from 'chart.js';
import { Chart } from 'react-chartjs-2';
import { fetchChartData, type DailyChartData } from '@/lib/api';

ChartJS.register(CategoryScale, LinearScale, BarElement, LineElement, PointElement, Title, Tooltip, Legend);

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
        backgroundColor: 'rgba(59, 130, 246, 0.7)',
        borderColor: 'rgba(59, 130, 246, 1)',
        borderWidth: 1,
        yAxisID: 'y',
        order: 2,
      },
      {
        type: 'line' as const,
        label: 'Deslizamientos',
        data: dailyData.map((d) => d.landslides),
        borderColor: 'rgba(239, 68, 68, 1)',
        backgroundColor: 'rgba(239, 68, 68, 0.2)',
        borderWidth: 2,
        pointRadius: 3,
        pointBackgroundColor: 'rgba(239, 68, 68, 1)',
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
        labels: { color: '#94a3b8', usePointStyle: true, padding: 20 },
      },
      title: {
        display: true,
        text: communeId ? `Lluvia vs Deslizamientos — Comuna ${communeId}` : 'Lluvia vs Deslizamientos (todas las comunas)',
        color: '#f1f5f9',
        font: { size: 14, weight: 'bold' as const },
        padding: { bottom: 16 },
      },
      tooltip: {
        backgroundColor: '#1e293b',
        titleColor: '#f1f5f9',
        bodyColor: '#94a3b8',
        borderColor: '#334155',
        borderWidth: 1,
        padding: 12,
      },
    },
    scales: {
      x: {
        grid: { color: 'rgba(51,65,85,0.5)' },
        ticks: { color: '#94a3b8', maxRotation: 45, minRotation: 45, font: { size: 10 } },
      },
      y: {
        type: 'linear' as const,
        position: 'left' as const,
        title: { display: true, text: 'Lluvia (mm)', color: '#3b82f6', font: { size: 12, weight: 'bold' as const } },
        grid: { color: 'rgba(51,65,85,0.5)' },
        ticks: { color: '#3b82f6' },
      },
      y1: {
        type: 'linear' as const,
        position: 'right' as const,
        title: { display: true, text: 'Deslizamientos', color: '#ef4444', font: { size: 12, weight: 'bold' as const } },
        grid: { drawOnChartArea: false },
        ticks: { color: '#ef4444', stepSize: 1 },
      },
    },
  };

  if (dailyData.length === 0) {
    return (
      <div className="bg-[#1e293b] rounded-lg p-6 border border-[#334155] h-[300px] flex items-center justify-center">
        <span className="text-[#94a3b8] text-sm">Cargando datos...</span>
      </div>
    );
  }

  return (
    <div className="bg-[#1e293b] rounded-lg p-6 border border-[#334155]">
      <div className="h-[300px]">
        <Chart type="bar" data={data} options={options} />
      </div>
    </div>
  );
}
