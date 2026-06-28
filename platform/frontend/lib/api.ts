const apiBase = (process.env.NEXT_PUBLIC_API_BASE ?? process.env.NEXT_PUBLIC_API_URL ?? '/api').replace(/\/$/, '');
const backendBase = apiBase.endsWith('/api') ? apiBase.slice(0, -4) || '/' : apiBase;

// ── Tipos ──────────────────────────────────────────────────────

export interface CommuneFeature {
  type: 'Feature';
  geometry: object | null;
  properties: {
    commune_id: string;
    nombre_comuna: string;
    comuna_nombre?: string;
    municipio?: string;
    parent_commune_id?: string;
    rain7d?: number;
    rain30d?: number;
    trend?: number;
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
  risk_score?: number | null;
  risk_level?: string;
}

export interface CommuneDetail {
  commune_id: string;
  nombre_comuna: string;
  risk_score: number | null;
  risk_level: string;
  predicted_at: string | null;
  rainfall_last_7d_total: number | string;
  rainfall_last_30d_total: number | string;
  rainfall_last_7d_daily: Array<{ date: string; rainfall: number }>;
  historical_events: Array<{ id: number; fecha: string; tipo_emergencia: string; barrio: string }>;
  is_zona_ladera: boolean;
  model_explanation: string;
}

export interface RiskStats {
  total_comunas_monitoreadas: number;
  comunas_riesgo_critico: number;
  comunas_riesgo_alto: number;
  total_eventos_ultimos_30_dias: number;
  tendencia_riesgo_semana: string;
  max_precipitacion_24h?: number;
}

export interface ChatContext {
  selected_comuna_id?: string | number;
  selected_comuna_name?: string;
  risk_level?: string;
}

export interface ChatHistoryMessage {
  id?: string;
  role: 'user' | 'assistant' | string;
  content: string;
  ts?: number;
}

// ── Rain monitor types ─────────────────────────────────────────────────────────

export interface RainSnapshot {
  time: string;
  snapshot_mm: number;
  acum_mm: number;
}

export interface RainCommuneData {
  commune_id: string;
  nombre_comuna: string;
  snapshots: RainSnapshot[];
  precip_acum_mm: number;
  threshold_mm: number;
  is_over_threshold: boolean;
  risk_score: number | null;
  risk_category: string | null;
}

export interface LiveRainfallResponse {
  date: string;
  updated_at: string;
  comunas: RainCommuneData[];
}

export interface ScatterPoint {
  rainfall_mm: number;
  n_events: number;
  date: string;
}

export interface SpearmanCommune {
  commune_id: string;
  nombre_comuna: string;
  rho: number | null;
  p_value: number | null;
  n_observations: number;
  scatter_data: ScatterPoint[];
}

export interface ThresholdEntry {
  commune_id: string;
  nombre_comuna: string;
  threshold_mm: number;
}

export interface AlertLogEntry {
  id: number;
  commune_id: string;
  nombre_comuna: string;
  triggered_at: string | null;
  precip_acum_mm: number | null;
  threshold_mm: number | null;
  risk_score: number | null;
  risk_category: string | null;
  status: string | null;
}

type RawCommune = {
  commune_id: string;
  nombre_comuna: string;
  categoria_riesgo: CommuneFeature['properties']['categoria_riesgo'];
  indice_riesgo: number;
  n_eventos: number;
  is_zona_ladera: boolean;
  geometry?: object | string | null;
};

export function normalizeRiskLevel(value: string): CommuneFeature['properties']['categoria_riesgo'] {
  const v = value.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase();
  if (v === 'critico') return 'Crítico';
  if (v === 'alto') return 'Alto';
  if (v === 'medio') return 'Medio';
  return 'Bajo';
}

async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${apiBase}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    cache: 'no-store',
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }

  return res.json() as Promise<T>;
}

function normalizeGeometry(geometry: RawCommune['geometry']): object | null {
  if (!geometry) return null;
  if (typeof geometry === 'string') {
    try {
      return JSON.parse(geometry) as object;
    } catch {
      return null;
    }
  }
  return geometry;
}

function toFeature(row: RawCommune): CommuneFeature {
  return {
    type: 'Feature',
    geometry: normalizeGeometry(row.geometry),
    properties: {
      commune_id: row.commune_id,
      nombre_comuna: row.nombre_comuna,
      categoria_riesgo: normalizeRiskLevel(String(row.categoria_riesgo)),
      indice_riesgo: row.indice_riesgo,
      n_eventos: row.n_eventos,
      is_zona_ladera: row.is_zona_ladera,
    },
  };
}

export async function fetchGeoJSON(): Promise<GeoJSONResponse> {
  const data = await apiRequest<GeoJSONResponse | RawCommune[] | { comunas: RawCommune[] }>('/risk/comunas');

  if ('type' in data && data.type === 'FeatureCollection') {
    return {
      ...data,
      features: data.features.map((f) => ({
        ...f,
        properties: {
          ...f.properties,
          categoria_riesgo: normalizeRiskLevel(String(f.properties?.categoria_riesgo ?? 'Bajo')),
        },
      })),
    };
  }

  const raw = data as RawCommune[] | { comunas: RawCommune[] };
  const comunas = Array.isArray(raw) ? raw : raw.comunas;
  return {
    type: 'FeatureCollection',
    features: comunas.map(toFeature),
  };
}

// ── Alertas ────────────────────────────────────────────────────

export async function fetchAlerts(): Promise<Alert[]> {
  const data = await apiRequest<Alert[] | { alerts: Alert[] }>('/risk/alerts');
  const output: Alert[] = Array.isArray(data) ? data : data.alerts;

  // Rojo primero
  output.sort((a, b) => (a.nivel === 'Rojo' ? -1 : 1) - (b.nivel === 'Rojo' ? -1 : 1));
  return output;
}

// ── Eventos → datos para el gráfico ───────────────────────────

export async function fetchChartData(communeId?: string | null): Promise<DailyChartData[]> {
  if (!communeId) return [];
  const history = await apiRequest<any>(`/risk/historia/${communeId}`);
  const daily = history?.daily_data ?? history?.series ?? [];
  if (Array.isArray(daily) && daily.length > 0) {
    return daily.slice(-30).map((d: any) => ({
      date: new Date(d.date ?? d.fecha).toLocaleDateString('es-CO', { day: '2-digit', month: 'short' }),
      rainfall: Number(d.rainfall ?? d.precipitacion_mm ?? 0),
      landslides: Number(d.landslides ?? d.n_eventos ?? 0),
      risk_score: d.risk_score ?? null,
      risk_level: d.risk_level ?? 'Sin datos',
    }));
  }
  return [];
}

export async function fetchCommuneDetail(communeId: string): Promise<CommuneDetail> {
  return apiRequest<CommuneDetail>(`/risk/comuna/${communeId}/detalle`);
}

export async function fetchRiskStats(): Promise<RiskStats> {
  return apiRequest<RiskStats>('/risk/estadisticas');
}

export async function fetchBackendHealth(): Promise<boolean> {
  const target = backendBase === '/' ? '' : backendBase;
  const res = await fetch(`${target}/`, { cache: 'no-store' });
  return res.ok;
}

// ── Chat (API TEYVA FastAPI) ───────────────────────────────────

export async function sendChatMessage(
  message: string,
  sessionId: string,
  context?: ChatContext | null
): Promise<string> {
  const data = await apiRequest<{ reply?: string; response?: string; answer?: string }>('/chat', {
    method: 'POST',
    body: JSON.stringify({ message, session_id: sessionId, context: context ?? null }),
  });
  return data.reply ?? data.response ?? data.answer ?? '';
}

export async function fetchChatHistory(sessionId: string): Promise<ChatHistoryMessage[]> {
  const data = await apiRequest<{ messages?: ChatHistoryMessage[]; history?: ChatHistoryMessage[] }>(
    `/chat/history/${sessionId}`
  );
  return data.messages ?? data.history ?? [];
}

// ── Rain monitor ───────────────────────────────────────────────────────────────

export async function fetchLiveRainfall(): Promise<LiveRainfallResponse> {
  return apiRequest<LiveRainfallResponse>('/rain/live');
}

export async function fetchSpearman(): Promise<{ comunas: SpearmanCommune[] }> {
  return apiRequest<{ comunas: SpearmanCommune[] }>('/rain/spearman');
}

export async function fetchRainThresholds(): Promise<{ thresholds: ThresholdEntry[] }> {
  return apiRequest<{ thresholds: ThresholdEntry[] }>('/rain/thresholds');
}

export async function setThreshold(communeId: string, thresholdMm: number): Promise<void> {
  await apiRequest<unknown>(`/rain/thresholds/${communeId}`, {
    method: 'PUT',
    body: JSON.stringify({ threshold_mm: thresholdMm }),
  });
}

export async function fetchWebhookSettings(): Promise<{ configured: boolean; masked_url: string | null }> {
  return apiRequest<{ configured: boolean; masked_url: string | null }>('/rain/settings/webhook');
}

export async function saveWebhook(url: string): Promise<void> {
  await apiRequest<unknown>('/rain/settings/webhook', {
    method: 'POST',
    body: JSON.stringify({ url }),
  });
}

export async function testWebhook(): Promise<{ ok: boolean; status?: string; response_code?: number }> {
  return apiRequest<{ ok: boolean; status?: string; response_code?: number }>(
    '/rain/settings/webhook/test',
    { method: 'POST', body: '{}' }
  );
}

export async function fetchAlertLog(): Promise<{ logs: AlertLogEntry[] }> {
  return apiRequest<{ logs: AlertLogEntry[] }>('/rain/alerts/log');
}

// ── Scraper health ─────────────────────────────────────────────────────────────

export interface ScraperSourceHealth {
  source: string;
  status: 'healthy' | 'warning' | 'critical' | 'unknown';
  last_success_at: string | null;
  consecutive_failures: number;
  success_rate_24h: number | null;
  data_lag_minutes: number | null;
  interval_minutes: number;
  total_runs_24h: number;
  last_run_status: string | null;
  last_run_at: string | null;
  last_records_valid: number | null;
  last_detail: string | null;
}

export interface ScraperHealthResponse {
  overall: 'healthy' | 'warning' | 'critical';
  sources: ScraperSourceHealth[];
  computed_at: string;
}

export interface ScraperRunEntry {
  id: number;
  status: string;
  run_started_at: string | null;
  run_finished_at: string | null;
  records_downloaded: number | null;
  records_valid: number | null;
  detail: string | null;
}

export interface ScraperTimelineResponse {
  sources: Record<string, ScraperRunEntry[]>;
}

export async function fetchScraperHealth(): Promise<ScraperHealthResponse> {
  return apiRequest<ScraperHealthResponse>('/scraper/health');
}

export async function fetchScraperTimeline(): Promise<ScraperTimelineResponse> {
  return apiRequest<ScraperTimelineResponse>('/scraper/timeline');
}
