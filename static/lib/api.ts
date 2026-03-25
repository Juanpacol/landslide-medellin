import { createClient } from '@supabase/supabase-js';

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
const supabaseKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

if (!supabaseUrl || !supabaseKey) {
  console.warn('⚠️ Variables de Supabase no configuradas: NEXT_PUBLIC_SUPABASE_URL y NEXT_PUBLIC_SUPABASE_ANON_KEY');
}

const supabase = createClient(
  supabaseUrl ?? '',
  supabaseKey ?? ''
);

// ── Tipos ──────────────────────────────────────────────────────

export interface CommuneFeature {
  type: 'Feature';
  geometry: object | null;
  properties: {
    commune_id: string;
    nombre_comuna: string;
    categoria_riesgo: 'Bajo' | 'Medio' | 'Alto' | 'Crítico';
    indice_riesgo: number;
    n_eventos: number;
    is_zona_ladera: boolean;
  };
}

export interface GeoJSONResponse {
  type: 'FeatureCollection';
  features: CommuneFeature[];
}

export interface Alert {
  id: number;
  commune_id: string;
  nombre_comuna: string;
  nivel: 'Rojo' | 'Naranja';
  precipitacion_7d: number;
  n_eventos_recientes: number | null;
  fecha_alerta: string;
}

export interface DailyChartData {
  date: string;
  rainfall: number;
  landslides: number;
}

// ── GeoJSON ────────────────────────────────────────────────────

export async function fetchGeoJSON(): Promise<GeoJSONResponse> {
  const { data, error } = await supabase
    .from('communes')
    .select('commune_id, nombre_comuna, categoria_riesgo, indice_riesgo, n_eventos, is_zona_ladera, geometry');

  if (error) throw new Error(error.message);

  const features: CommuneFeature[] = (data || []).map((row) => {
    let geometry = null;
    try {
      geometry = typeof row.geometry === 'string' ? JSON.parse(row.geometry) : row.geometry;
    } catch { /* sin geometría */ }

    return {
      type: 'Feature',
      geometry,
      properties: {
        commune_id: row.commune_id,
        nombre_comuna: row.nombre_comuna,
        categoria_riesgo: row.categoria_riesgo,
        indice_riesgo: row.indice_riesgo,
        n_eventos: row.n_eventos,
        is_zona_ladera: row.is_zona_ladera,
      },
    };
  });

  return { type: 'FeatureCollection', features };
}

// ── Alertas ────────────────────────────────────────────────────

export async function fetchAlerts(): Promise<Alert[]> {
  const { data, error } = await supabase
    .from('alerts')
    .select('id, commune_id, nivel, precipitacion_valor, tipo_umbral, timestamp, communes(nombre_comuna)')
    .order('nivel', { ascending: true });

  if (error) throw new Error(error.message);

  const output: Alert[] = (data || []).map((a: any) => ({
    id: a.id,
    commune_id: a.commune_id,
    nombre_comuna: a.communes?.nombre_comuna ?? a.commune_id,
    nivel: a.nivel,
    precipitacion_7d: a.precipitacion_valor,
    n_eventos_recientes: null,
    fecha_alerta: a.timestamp,
  }));

  // Rojo primero
  output.sort((a, b) => (a.nivel === 'Rojo' ? -1 : 1) - (b.nivel === 'Rojo' ? -1 : 1));
  return output;
}

// ── Eventos → datos para el gráfico ───────────────────────────

export async function fetchChartData(communeId?: string | null): Promise<DailyChartData[]> {
  let query = supabase
    .from('events')
    .select('fecha, commune_id')
    .order('fecha', { ascending: true });

  if (communeId) {
    query = query.eq('commune_id', communeId);
  }

  const { data, error } = await query;
  if (error) throw new Error(error.message);

  // Contar eventos por fecha
  const countByDate: Record<string, number> = {};
  for (const e of data || []) {
    const day = (e.fecha ?? '').slice(0, 10);
    if (day) countByDate[day] = (countByDate[day] ?? 0) + 1;
  }

  // Precipitación: traer últimos 30 días disponibles
  const { data: precip } = await supabase
    .from('precipitation')
    .select('fecha, precipitacion_mm')
    .eq('estacion', 'Niquía')
    .order('fecha', { ascending: false })
    .limit(30);

  const precipByDate: Record<string, number> = {};
  for (const p of precip || []) {
    precipByDate[p.fecha] = p.precipitacion_mm;
  }

  const allDates = Array.from(
    new Set([...Object.keys(countByDate), ...Object.keys(precipByDate)])
  ).sort().slice(-30);

  return allDates.map((day) => ({
    date: new Date(day).toLocaleDateString('es-CO', { day: '2-digit', month: 'short' }),
    rainfall: precipByDate[day] ?? 0,
    landslides: countByDate[day] ?? 0,
  }));
}
