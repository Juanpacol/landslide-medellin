'use client';

import dynamic from 'next/dynamic';

// Leaflet toca `window` al importarse: solo puede montarse en el cliente.
// El chunk (incluye los ~790KB del GeoJSON de barrios) se descarga únicamente
// cuando el usuario activa la vista de barrios.
export const BarriosMap = dynamic(() => import('./barrios-map-inner'), {
  ssr: false,
  loading: () => (
    <div
      className="flex h-full w-full items-center justify-center"
      style={{
        borderRadius: '24px',
        border: '1px solid var(--border)',
        background: 'var(--card)',
        color: 'var(--muted-foreground)',
        fontSize: '13.5px',
      }}
    >
      Cargando mapa de barrios…
    </div>
  ),
});
