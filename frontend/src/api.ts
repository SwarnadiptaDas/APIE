import axios from 'axios';
import type {
  ActionResult,
  AnalysisResult,
  Incident,
  MetricDataPoint,
} from './types';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000';

const api = axios.create({
  baseURL: API_URL,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

// ─── Incidents API ─────────────────────────────────────────────────────────────
export const incidentsApi = {
  list: async (limit = 50): Promise<Incident[]> => {
    const res = await api.get<{ incidents: Incident[] }>('/incidents/', { params: { limit } });
    return res.data.incidents;
  },

  get: async (id: string): Promise<Incident> => {
    const res = await api.get<Incident>(`/incidents/${id}`);
    return res.data;
  },

  trigger: async (params: {
    service: string;
    metric_name: string;
    severity: string;
    value: number;
    affected_services: string[];
    anomaly_data?: Record<string, unknown>;
  }): Promise<{ incident_id: string; status: string }> => {
    const res = await api.post('/incidents/trigger', params);
    return res.data;
  },

  executeAction: async (
    incidentId: string,
    actionId: string,
    params: Record<string, unknown> = {}
  ): Promise<ActionResult> => {
    const res = await api.post<ActionResult>(
      `/incidents/${incidentId}/actions/${actionId}`,
      { params }
    );
    return res.data;
  },

  resolve: async (id: string): Promise<{ status: string; resolution_minutes: number }> => {
    const res = await api.post(`/incidents/${id}/resolve`);
    return res.data;
  },

  getPostmortem: async (id: string): Promise<{ postmortem: string }> => {
    const res = await api.get(`/incidents/${id}/postmortem`);
    return res.data;
  },
};

const TELEMETRY_URL = import.meta.env.VITE_TELEMETRY_URL || 'http://localhost:8001';

// ─── Metrics API ───────────────────────────────────────────────────────────────
export const metricsApi = {
  query: async (params: {
    service?: string;
    metric_name?: string;
    start_time?: number;
    end_time?: number;
    limit?: number;
  }): Promise<MetricDataPoint[]> => {
    const res = await api.get<{ metrics: MetricDataPoint[] }>(
      `${TELEMETRY_URL}/v1/metrics/query`,
      { params }
    );
    return res.data.metrics;
  },
};

// ─── Health API ────────────────────────────────────────────────────────────────
export const healthApi = {
  check: async (): Promise<{ status: string }> => {
    const res = await api.get('/health');
    return res.data;
  },

  stats: async (): Promise<Record<string, unknown>> => {
    const res = await api.get('/stats');
    return res.data;
  },
};

// ─── WebSocket Factory ────────────────────────────────────────────────────────
export function createIncidentWebSocket(
  onMessage: (data: unknown) => void,
  onOpen?: () => void,
  onClose?: () => void
): WebSocket {
  const wsUrl = `${WS_URL}/ws/incidents`;
  const ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    console.log('[WS] Connected to incident stream');
    onOpen?.();
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      onMessage(data);
    } catch (err) {
      console.warn('[WS] Failed to parse message:', err);
    }
  };

  ws.onclose = () => {
    console.log('[WS] Disconnected');
    onClose?.();
  };

  ws.onerror = (err) => {
    console.error('[WS] Error:', err);
  };

  return ws;
}

export default api;
