'use client';

import {
  CategoryScale,
  Chart as ChartJS,
  Legend,
  LinearScale,
  LineController,
  LineElement,
  PointElement,
  ScatterController,
  Title,
  Tooltip,
} from 'chart.js';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Chart } from 'react-chartjs-2';
import {
  fetchAlertLog,
  fetchLiveRainfall,
  fetchRainThresholds,
  fetchSpearman,
  fetchWebhookSettings,
  saveWebhook,
  setThreshold,
  testWebhook,
  type AlertLogEntry,
  type LiveRainfallResponse,
  type RainCommuneData,
  type SpearmanCommune,
  type ThresholdEntry,
} from '@/lib/api';

ChartJS.register(
  CategoryScale,
  LinearScale,
  LineElement,
  LineController,
  PointElement,
  ScatterController,
  Title,
  Tooltip,
  Legend,
);

const CARD: React.CSSProperties = {
  borderRadius: '18px',
  background: 'oklch(0.99 0.006 75)',
  border: '1px solid oklch(0.91 0.018 70)',
  padding: '22px 24px',
};

const LABEL: React.CSSProperties = {
  fontSize: '11px',
  fontWeight: 700,
  textTransform: 'uppercase' as const,
  letterSpacing: '0.12em',
  color: 'oklch(0.55 0.035 55)',
  marginBottom: '14px',
};

function riskColor(category: string | null | undefined): string {
  if (!category) return 'oklch(0.65 0.03 55)';
  const c = category.toLowerCase().normalize('NFD').replace(/\p{Diacritic}/gu, '');
  if (c === 'critico') return 'oklch(0.62 0.22 25)';
  if (c === 'alto') return 'oklch(0.68 0.15 45)';
  if (c === 'medio') return 'oklch(0.72 0.12 70)';
  return 'oklch(0.65 0.13 140)';
}

function statusColor(status: string | null | undefined): string {
  if (status === 'sent') return 'oklch(0.65 0.13 140)';
  if (status === 'failed') return 'oklch(0.62 0.22 25)';
  return 'oklch(0.72 0.12 70)';
}

// ── Chart A: acumulado diario ──────────────────────────────────────────────────

function AccumChart({ data, selectedId }: { data: LiveRainfallResponse | null; selectedId: string }) {
  const selected = data?.comunas.find((c) => c.commune_id === selectedId);

  const snapshots = selected?.snapshots ?? [];
  const labels = snapshots.map((s) => s.time);
  const acumValues = snapshots.map((s) => s.acum_mm);
  const threshold = selected?.threshold_mm ?? 35;

  const chartData = {
    labels,
    datasets: [
      {
        type: 'line' as const,
        label: `${selected?.nombre_comuna ?? '—'} (acumulado mm)`,
        data: acumValues,
        borderColor: 'oklch(0.55 0.16 245)',
        backgroundColor: 'oklch(0.55 0.16 245 / 0.12)',
        fill: true,
        tension: 0.35,
        pointRadius: 3,
        borderWidth: 2.5,
        yAxisID: 'y',
      },
      {
        type: 'line' as const,
        label: `Umbral (${threshold} mm)`,
        data: labels.map(() => threshold),
        borderColor: 'oklch(0.62 0.22 25)',
        borderDash: [6, 4],
        borderWidth: 2,
        pointRadius: 0,
        fill: false,
        yAxisID: 'y',
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index' as const, intersect: false },
    plugins: {
      legend: { position: 'top' as const, labels: { boxWidth: 12, font: { size: 12 } } },
      tooltip: {
        callbacks: {
          label: (ctx: any) => ` ${ctx.dataset.label}: ${ctx.parsed.y} mm`,
        },
      },
    },
    scales: {
      x: { grid: { display: false }, ticks: { maxTicksLimit: 12, font: { size: 11 } } },
      y: {
        title: { display: true, text: 'mm acumulados', font: { size: 11 } },
        beginAtZero: true,
        grid: { color: 'oklch(0.91 0.018 70)' },
        ticks: { font: { size: 11 } },
      },
    },
  };

  if (!snapshots.length) {
    return (
      <div style={{ height: '280px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'oklch(0.6 0.03 55)', fontSize: '14px' }}>
        Sin datos de lluvia para hoy. El scraper SIATA actualiza cada 30 min.
      </div>
    );
  }

  return (
    <div style={{ height: '280px' }}>
      <Chart type="line" data={chartData as any} options={options} />
    </div>
  );
}

// ── Chart B: scatter Spearman ──────────────────────────────────────────────────

function SpearmanChart({ data, selectedId }: { data: SpearmanCommune[] | null; selectedId: string }) {
  const commune = data?.find((c) => c.commune_id === selectedId);

  const chartData = {
    datasets: [
      {
        type: 'scatter' as const,
        label: commune?.nombre_comuna ?? '—',
        data: (commune?.scatter_data ?? []).map((p) => ({ x: p.rainfall_mm, y: p.n_events })),
        backgroundColor: 'oklch(0.55 0.16 245 / 0.55)',
        borderColor: 'oklch(0.55 0.16 245)',
        pointRadius: 5,
        pointHoverRadius: 7,
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          label: (ctx: any) => ` ${ctx.parsed.x} mm → ${ctx.parsed.y} eventos`,
        },
      },
    },
    scales: {
      x: {
        title: { display: true, text: 'Lluvia diaria promedio (mm)', font: { size: 11 } },
        grid: { color: 'oklch(0.91 0.018 70)' },
        ticks: { font: { size: 11 } },
      },
      y: {
        title: { display: true, text: 'Eventos de deslizamiento', font: { size: 11 } },
        beginAtZero: true,
        ticks: { stepSize: 1, font: { size: 11 } },
      },
    },
  };

  const hasData = (commune?.scatter_data?.length ?? 0) >= 2;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Rho badge */}
      <div style={{ display: 'flex', gap: '10px', marginBottom: '12px', flexWrap: 'wrap' }}>
        <div style={{ borderRadius: '10px', background: 'oklch(0.93 0.02 245)', padding: '6px 13px', fontSize: '13px', fontWeight: 700, color: 'oklch(0.35 0.12 245)' }}>
          ρ = {commune?.rho != null ? commune.rho.toFixed(3) : 'N/A'}
        </div>
        <div style={{ borderRadius: '10px', background: 'oklch(0.94 0.014 75)', padding: '6px 13px', fontSize: '12px', color: 'oklch(0.45 0.03 55)' }}>
          p = {commune?.p_value != null ? commune.p_value : 'N/A'}
        </div>
        <div style={{ borderRadius: '10px', background: 'oklch(0.94 0.014 75)', padding: '6px 13px', fontSize: '12px', color: 'oklch(0.45 0.03 55)' }}>
          n = {commune?.n_observations ?? 0} días
        </div>
      </div>

      <div style={{ flex: 1, minHeight: 0 }}>
        {hasData ? (
          <Chart type="scatter" data={chartData as any} options={options} />
        ) : (
          <div style={{ height: '200px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'oklch(0.6 0.03 55)', fontSize: '13px' }}>
            Insuficientes datos históricos para calcular correlación.
          </div>
        )}
      </div>
    </div>
  );
}

// ── Threshold settings table ───────────────────────────────────────────────────

function ThresholdSettings({
  thresholds,
  liveData,
  onSaved,
}: {
  thresholds: ThresholdEntry[];
  liveData: LiveRainfallResponse | null;
  onSaved: () => void;
}) {
  const [editing, setEditing] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState<string | null>(null);

  const acumMap: Record<string, number> = {};
  liveData?.comunas.forEach((c) => { acumMap[c.commune_id] = c.precip_acum_mm; });

  const handleSave = async (communeId: string, current: number) => {
    const val = parseFloat(editing[communeId] ?? String(current));
    if (isNaN(val) || val <= 0) return;
    setSaving(communeId);
    try {
      await setThreshold(communeId, val);
      onSaved();
    } finally {
      setSaving(null);
      setEditing((prev) => { const n = { ...prev }; delete n[communeId]; return n; });
    }
  };

  return (
    <div style={{ overflowY: 'auto', maxHeight: '320px' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
        <thead>
          <tr style={{ borderBottom: '1px solid oklch(0.89 0.018 70)' }}>
            {['Comuna', 'Hoy (mm)', 'Umbral (mm)', ''].map((h) => (
              <th key={h} style={{ padding: '8px 10px', textAlign: 'left', fontWeight: 600, color: 'oklch(0.5 0.03 55)', fontSize: '11px', whiteSpace: 'nowrap' }}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {thresholds.map((t) => {
            const acum = acumMap[t.commune_id] ?? 0;
            const pct = Math.min(100, Math.round((acum / t.threshold_mm) * 100));
            const over = acum > t.threshold_mm;
            return (
              <tr key={t.commune_id} style={{ borderBottom: '1px solid oklch(0.93 0.012 75)' }}>
                <td style={{ padding: '9px 10px', fontWeight: 500 }}>{t.nombre_comuna}</td>
                <td style={{ padding: '9px 10px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <div style={{ flex: 1, height: '6px', borderRadius: '99px', background: 'oklch(0.91 0.018 70)', overflow: 'hidden', minWidth: '50px' }}>
                      <div style={{ width: `${pct}%`, height: '100%', background: over ? 'oklch(0.62 0.22 25)' : 'oklch(0.55 0.16 245)', borderRadius: '99px', transition: 'width 0.3s' }} />
                    </div>
                    <span style={{ fontSize: '12px', minWidth: '36px', color: over ? 'oklch(0.5 0.18 25)' : 'inherit', fontWeight: over ? 700 : 400 }}>
                      {acum.toFixed(1)}
                    </span>
                  </div>
                </td>
                <td style={{ padding: '9px 10px' }}>
                  <input
                    type="number"
                    min={1}
                    step={0.5}
                    value={editing[t.commune_id] ?? t.threshold_mm}
                    onChange={(e) => setEditing((prev) => ({ ...prev, [t.commune_id]: e.target.value }))}
                    style={{
                      width: '72px',
                      padding: '5px 8px',
                      borderRadius: '8px',
                      border: '1px solid oklch(0.87 0.02 70)',
                      background: 'oklch(0.98 0.006 75)',
                      fontSize: '13px',
                      color: 'oklch(0.28 0.04 45)',
                    }}
                  />
                </td>
                <td style={{ padding: '9px 10px' }}>
                  <button
                    onClick={() => handleSave(t.commune_id, t.threshold_mm)}
                    disabled={saving === t.commune_id || !(t.commune_id in editing)}
                    style={{
                      padding: '5px 12px',
                      borderRadius: '8px',
                      border: 'none',
                      background: t.commune_id in editing ? 'oklch(0.55 0.16 245)' : 'oklch(0.92 0.02 70)',
                      color: t.commune_id in editing ? 'white' : 'oklch(0.6 0.03 55)',
                      fontSize: '12px',
                      fontWeight: 600,
                      cursor: t.commune_id in editing ? 'pointer' : 'default',
                      transition: 'all 0.15s',
                    }}
                  >
                    {saving === t.commune_id ? '…' : 'Guardar'}
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── Webhook config ─────────────────────────────────────────────────────────────

function WebhookConfig() {
  const [maskedUrl, setMaskedUrl] = useState<string | null>(null);
  const [configured, setConfigured] = useState(false);
  const [newUrl, setNewUrl] = useState('');
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);

  useEffect(() => {
    fetchWebhookSettings().then((r) => {
      setConfigured(r.configured);
      setMaskedUrl(r.masked_url);
    }).catch(() => {});
  }, []);

  const handleSave = async () => {
    if (!newUrl.startsWith('https://hooks.slack.com/')) return;
    setSaving(true);
    try {
      await saveWebhook(newUrl);
      setConfigured(true);
      setMaskedUrl(newUrl.slice(0, 30) + '…' + newUrl.slice(-8));
      setNewUrl('');
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const r = await testWebhook();
      setTestResult(r.ok ? '✓ Mensaje enviado a Slack' : `✗ Error: ${r.status ?? 'desconocido'}`);
    } catch {
      setTestResult('✗ Error de conexión');
    } finally {
      setTesting(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
      {configured && maskedUrl && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '10px 14px', borderRadius: '10px', background: 'oklch(0.93 0.06 140 / 0.15)', border: '1px solid oklch(0.8 0.08 140 / 0.3)' }}>
          <span style={{ color: 'oklch(0.5 0.1 140)', fontSize: '13px' }}>✓ Configurado:</span>
          <code style={{ fontSize: '12px', color: 'oklch(0.4 0.05 55)', fontFamily: 'monospace' }}>{maskedUrl}</code>
        </div>
      )}
      <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
        <input
          type="url"
          placeholder="https://hooks.slack.com/services/…"
          value={newUrl}
          onChange={(e) => setNewUrl(e.target.value)}
          style={{
            flex: 1,
            minWidth: '260px',
            padding: '9px 14px',
            borderRadius: '10px',
            border: '1px solid oklch(0.87 0.02 70)',
            background: 'oklch(0.98 0.006 75)',
            fontSize: '13px',
            color: 'oklch(0.28 0.04 45)',
          }}
        />
        <button
          onClick={handleSave}
          disabled={saving || !newUrl.startsWith('https://hooks.slack.com/')}
          style={{
            padding: '9px 18px',
            borderRadius: '10px',
            border: 'none',
            background: newUrl.startsWith('https://hooks.slack.com/') ? 'oklch(0.38 0.08 38)' : 'oklch(0.9 0.02 70)',
            color: newUrl.startsWith('https://hooks.slack.com/') ? 'white' : 'oklch(0.6 0.03 55)',
            fontSize: '13px',
            fontWeight: 600,
            cursor: newUrl.startsWith('https://hooks.slack.com/') ? 'pointer' : 'default',
          }}
        >
          {saving ? 'Guardando…' : 'Guardar'}
        </button>
        {configured && (
          <button
            onClick={handleTest}
            disabled={testing}
            style={{
              padding: '9px 18px',
              borderRadius: '10px',
              border: '1px solid oklch(0.87 0.02 70)',
              background: 'oklch(0.97 0.012 75)',
              color: 'oklch(0.38 0.06 45)',
              fontSize: '13px',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            {testing ? 'Enviando…' : 'Probar alerta'}
          </button>
        )}
      </div>
      {testResult && (
        <div style={{ fontSize: '13px', color: testResult.startsWith('✓') ? 'oklch(0.5 0.1 140)' : 'oklch(0.5 0.18 25)', fontWeight: 600 }}>
          {testResult}
        </div>
      )}
    </div>
  );
}

// ── Alert log ──────────────────────────────────────────────────────────────────

function AlertLog({ logs }: { logs: AlertLogEntry[] }) {
  if (!logs.length) {
    return <p style={{ fontSize: '13px', color: 'oklch(0.6 0.03 55)' }}>Sin alertas registradas aún.</p>;
  }
  return (
    <div style={{ overflowY: 'auto', maxHeight: '200px' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
        <thead>
          <tr style={{ borderBottom: '1px solid oklch(0.89 0.018 70)' }}>
            {['Hora (Col)', 'Comuna', 'Lluvia', 'Umbral', 'Riesgo', 'Estado'].map((h) => (
              <th key={h} style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 600, color: 'oklch(0.5 0.03 55)', whiteSpace: 'nowrap' }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {logs.map((l) => (
            <tr key={l.id} style={{ borderBottom: '1px solid oklch(0.93 0.012 75)' }}>
              <td style={{ padding: '6px 8px', whiteSpace: 'nowrap', color: 'oklch(0.5 0.03 55)' }}>
                {l.triggered_at ? new Date(l.triggered_at).toLocaleString('es-CO', { timeZone: 'America/Bogota', hour: '2-digit', minute: '2-digit', day: '2-digit', month: 'short' }) : '—'}
              </td>
              <td style={{ padding: '6px 8px', fontWeight: 600 }}>{l.nombre_comuna}</td>
              <td style={{ padding: '6px 8px' }}>{l.precip_acum_mm?.toFixed(1) ?? '—'} mm</td>
              <td style={{ padding: '6px 8px' }}>{l.threshold_mm?.toFixed(1) ?? '—'} mm</td>
              <td style={{ padding: '6px 8px' }}>
                <span style={{ color: riskColor(l.risk_category), fontWeight: 600, fontSize: '11px' }}>
                  {l.risk_category ?? '—'}
                </span>
              </td>
              <td style={{ padding: '6px 8px' }}>
                <span style={{
                  display: 'inline-block',
                  padding: '2px 8px',
                  borderRadius: '99px',
                  fontSize: '11px',
                  fontWeight: 700,
                  background: `${statusColor(l.status)} / 0.15`,
                  color: statusColor(l.status),
                  border: `1px solid ${statusColor(l.status)} / 0.3`,
                }}>
                  {l.status ?? '—'}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Main RainMonitor component ─────────────────────────────────────────────────

export function RainMonitor() {
  const [liveData, setLiveData] = useState<LiveRainfallResponse | null>(null);
  const [spearmanData, setSpearmanData] = useState<SpearmanCommune[] | null>(null);
  const [thresholds, setThresholds] = useState<ThresholdEntry[]>([]);
  const [alertLogs, setAlertLogs] = useState<AlertLogEntry[]>([]);
  const [selectedId, setSelectedId] = useState('3'); // Manrique como default (zona ladera)
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    try {
      const [live, spearman, thresh, logs] = await Promise.all([
        fetchLiveRainfall(),
        fetchSpearman(),
        fetchRainThresholds(),
        fetchAlertLog(),
      ]);
      setLiveData(live);
      setSpearmanData(spearman.comunas);
      setThresholds(thresh.thresholds);
      setAlertLogs(logs.logs);
      setLastUpdated(new Date());
    } catch {
      // keep stale data
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    // Auto-refresh every 30 min to match SIATA update cycle
    intervalRef.current = setInterval(() => void load(), 30 * 60 * 1000);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [load]);

  const selectedCommune = liveData?.comunas.find((c) => c.commune_id === selectedId);
  const overThreshold = liveData?.comunas.filter((c) => c.is_over_threshold) ?? [];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>

      {/* ── Header ── */}
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: '12px' }}>
        <div>
          <h2 style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '26px', letterSpacing: '-0.02em', color: 'oklch(0.28 0.04 45)', margin: 0 }}>
            Monitor de Lluvia
          </h2>
          <p style={{ margin: '4px 0 0', fontSize: '13px', color: 'oklch(0.55 0.03 55)' }}>
            Acumulado diario · SIATA · actualización cada 30 min
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {lastUpdated && (
            <span style={{ fontSize: '12px', color: 'oklch(0.6 0.03 55)' }}>
              Actualizado: {lastUpdated.toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit' })}
            </span>
          )}
          <button
            onClick={() => void load()}
            style={{
              padding: '8px 16px',
              borderRadius: '10px',
              border: '1px solid oklch(0.87 0.02 70)',
              background: 'oklch(0.97 0.012 75)',
              fontSize: '13px',
              fontWeight: 600,
              cursor: 'pointer',
              color: 'oklch(0.38 0.06 45)',
            }}
          >
            ↻ Actualizar
          </button>
        </div>
      </div>

      {/* ── Alert banners for over-threshold communes ── */}
      {overThreshold.length > 0 && (
        <div style={{
          borderRadius: '14px',
          background: 'oklch(0.62 0.22 25 / 0.08)',
          border: '1px solid oklch(0.62 0.22 25 / 0.3)',
          padding: '14px 18px',
          display: 'flex',
          flexWrap: 'wrap',
          gap: '8px',
          alignItems: 'center',
        }}>
          <span style={{ fontWeight: 700, fontSize: '13px', color: 'oklch(0.45 0.18 25)' }}>
            ⚠ {overThreshold.length} comuna{overThreshold.length > 1 ? 's' : ''} sobre umbral hoy:
          </span>
          {overThreshold.map((c) => (
            <button
              key={c.commune_id}
              onClick={() => setSelectedId(c.commune_id)}
              style={{
                padding: '4px 12px',
                borderRadius: '99px',
                border: '1px solid oklch(0.62 0.22 25 / 0.4)',
                background: selectedId === c.commune_id ? 'oklch(0.62 0.22 25)' : 'oklch(0.62 0.22 25 / 0.12)',
                color: selectedId === c.commune_id ? 'white' : 'oklch(0.45 0.18 25)',
                fontSize: '12px',
                fontWeight: 700,
                cursor: 'pointer',
              }}
            >
              {c.nombre_comuna} · {c.precip_acum_mm.toFixed(1)} mm
            </button>
          ))}
        </div>
      )}

      {/* ── Commune selector + stats row ── */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <label style={{ fontSize: '13px', fontWeight: 600, color: 'oklch(0.45 0.03 55)' }}>
            Seleccionar comuna:
          </label>
          <select
            value={selectedId}
            onChange={(e) => setSelectedId(e.target.value)}
            style={{
              padding: '8px 12px',
              borderRadius: '10px',
              border: '1px solid oklch(0.87 0.02 70)',
              background: 'oklch(0.98 0.006 75)',
              fontSize: '13px',
              color: 'oklch(0.28 0.04 45)',
              cursor: 'pointer',
            }}
          >
            {(liveData?.comunas ?? []).map((c) => (
              <option key={c.commune_id} value={c.commune_id}>
                {c.nombre_comuna} — {c.precip_acum_mm.toFixed(1)} mm
                {c.is_over_threshold ? ' ⚠' : ''}
              </option>
            ))}
          </select>
        </div>

        {/* Quick stats for selected commune */}
        {selectedCommune && (
          <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
            {[
              { label: 'Acumulado hoy', value: `${selectedCommune.precip_acum_mm.toFixed(1)} mm` },
              { label: 'Umbral', value: `${selectedCommune.threshold_mm.toFixed(1)} mm` },
              {
                label: 'Riesgo ML',
                value: selectedCommune.risk_category ?? 'Sin datos',
                color: riskColor(selectedCommune.risk_category),
              },
            ].map((s) => (
              <div key={s.label} style={{
                borderRadius: '12px',
                background: 'oklch(0.96 0.012 75)',
                border: '1px solid oklch(0.91 0.018 70)',
                padding: '8px 14px',
              }}>
                <div style={{ fontSize: '10.5px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'oklch(0.55 0.03 55)' }}>
                  {s.label}
                </div>
                <div style={{ fontSize: '17px', fontWeight: 700, color: s.color ?? 'oklch(0.28 0.04 45)', marginTop: '2px' }}>
                  {s.value}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Chart A: Acumulado diario ── */}
      <div style={CARD}>
        <div style={LABEL}>Lluvia acumulada hoy (desde medianoche, hora Colombia)</div>
        {loading ? (
          <div style={{ height: '280px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'oklch(0.6 0.03 55)' }}>
            Cargando datos…
          </div>
        ) : (
          <AccumChart data={liveData} selectedId={selectedId} />
        )}
      </div>

      {/* ── Charts B + Thresholds ── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '18px' }}>
        <div style={{ ...CARD, display: 'flex', flexDirection: 'column', minHeight: '360px' }}>
          <div style={LABEL}>
            Correlación lluvia ↔ deslizamientos · Spearman
          </div>
          <div style={{ flex: 1 }}>
            <SpearmanChart data={spearmanData} selectedId={selectedId} />
          </div>
          <p style={{ margin: '10px 0 0', fontSize: '11.5px', color: 'oklch(0.6 0.03 55)', lineHeight: 1.5 }}>
            Cada punto = un día histórico. ρ cercano a 1 indica que a mayor lluvia, más eventos de deslizamiento.
            Valores significativos (p &lt; 0.05) sugieren que el umbral está bien calibrado para esta comuna.
          </p>
        </div>

        <div style={CARD}>
          <div style={LABEL}>Umbrales de alerta por comuna (mm/día)</div>
          <ThresholdSettings
            thresholds={thresholds}
            liveData={liveData}
            onSaved={load}
          />
        </div>
      </div>

      {/* ── Slack webhook config ── */}
      <div style={CARD}>
        <div style={LABEL}>Webhook de Slack</div>
        <p style={{ margin: '0 0 14px', fontSize: '13px', color: 'oklch(0.5 0.03 55)' }}>
          Cuando una comuna supere su umbral diario, TEYVA enviará un mensaje a tu canal de Slack.
          Las alertas tienen un cooldown de 6 horas por comuna para evitar ruido.
        </p>
        <WebhookConfig />
      </div>

      {/* ── Alert log ── */}
      <div style={CARD}>
        <div style={LABEL}>Historial de alertas (últimas 50)</div>
        <AlertLog logs={alertLogs} />
      </div>
    </div>
  );
}
