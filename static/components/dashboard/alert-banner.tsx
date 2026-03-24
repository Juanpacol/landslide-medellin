'use client';

import { useEffect, useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import { fetchAlerts, type Alert } from '@/lib/api';

export function AlertBanner() {
  const [alerts, setAlerts] = useState<Alert[]>([]);

  useEffect(() => {
    fetchAlerts()
      .then(setAlerts)
      .catch(() => setAlerts([]));
  }, []);

  return (
    <div className="bg-[#1e293b] border-b border-[#334155] px-4 py-3">
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 text-[#f59e0b]">
          <AlertTriangle className="h-5 w-5" />
          <span className="font-semibold text-sm uppercase tracking-wide">
            Alertas Activas
          </span>
        </div>
        <div className="h-5 w-px bg-[#475569]" />
        <div className="flex flex-wrap items-center gap-3">
          {alerts.length === 0 && (
            <span className="text-[#94a3b8] text-sm">Sin alertas activas</span>
          )}
          {alerts.map((alert) => (
            <div
              key={alert.id}
              className="flex items-center gap-2 bg-[#0f172a] rounded-lg px-3 py-1.5"
            >
              <span
                className={`px-2 py-0.5 rounded text-xs font-bold uppercase ${
                  alert.nivel === 'Rojo'
                    ? 'bg-[#ef4444] text-white'
                    : 'bg-[#f97316] text-white'
                }`}
              >
                {alert.nivel === 'Rojo' ? 'Alerta Roja' : 'Alerta Naranja'}
              </span>
              <span className="text-[#f1f5f9] text-sm font-medium">
                {alert.nombre_comuna}
              </span>
              <span className="text-[#94a3b8] text-sm">
                {alert.precipitacion_7d} mm
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
