'use client';

import dynamic from 'next/dynamic';

// Mismo patrón que barrios-map.tsx: Leaflet solo en cliente.
export const MeshMap = dynamic(() => import('./mesh-map-inner'), {
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
      Cargando cuadrículas…
    </div>
  ),
});
