import React, { useEffect, useRef, useState } from 'react';
import type { AnomalyEvent, WsMessage } from '../types';

interface AnomalyFeedProps {
  maxItems?: number;
}

const AnomalyFeed: React.FC<AnomalyFeedProps> = ({ maxItems = 50 }) => {
  const [events, setEvents] = useState<AnomalyEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Seed with mock events for demo
    const mockEvents: AnomalyEvent[] = Array.from({ length: 5 }, (_, i) => ({
      event_type: 'anomaly_detected',
      incident_id: `mock-${i}`,
      service: ['api-gateway', 'payment-service', 'order-service', 'auth-service', 'inventory-service'][i],
      metric_name: ['latency_p95_ms', 'error_rate', 'cpu_usage', 'memory_usage', 'latency_p95_ms'][i],
      severity: (['critical', 'warning', 'warning', 'critical', 'warning'][i]) as 'critical' | 'warning' | 'info',
      value: [8500, 0.12, 0.88, 0.92, 6200][i],
      baseline: [200, 0.01, 0.35, 0.55, 200][i],
      deviation_sigma: [4.2, 5.5, 3.1, 3.8, 3.6][i],
      timestamp: Date.now() / 1000 - (i * 120),
      detected_at: Date.now() / 1000 - (i * 120),
    }));
    setEvents(mockEvents);
    setConnected(true);
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [events]);

  const formatTime = (ts: number) => {
    return new Date(ts * 1000).toLocaleTimeString('en-US', { hour12: false });
  };

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'critical': return 'text-red-400 bg-red-500/10 border-red-500/30';
      case 'warning': return 'text-yellow-400 bg-yellow-500/10 border-yellow-500/30';
      default: return 'text-blue-400 bg-blue-500/10 border-blue-500/30';
    }
  };

  const formatValue = (event: AnomalyEvent) => {
    const metric = event.metric_name.toLowerCase();
    if (metric.includes('latency') || metric.includes('duration')) {
      return `${event.value.toFixed(0)}ms (baseline: ${event.baseline.toFixed(0)}ms)`;
    }
    if (metric.includes('error_rate') || metric.includes('cpu') || metric.includes('memory')) {
      return `${(event.value * 100).toFixed(1)}% (baseline: ${(event.baseline * 100).toFixed(1)}%)`;
    }
    return `${event.value.toFixed(2)} (baseline: ${event.baseline.toFixed(2)})`;
  };

  return (
    <div className="glass-card p-4 h-80 flex flex-col">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-white">Live Anomaly Feed</h3>
        <div className="flex items-center gap-2">
          <span className={`pulse-dot ${connected ? 'success' : 'warning'}`} />
          <span className="text-xs text-slate-400">{connected ? 'Connected' : 'Connecting...'}</span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto space-y-2 font-mono">
        {events.length === 0 ? (
          <div className="text-center text-slate-500 py-8 text-xs">
            No anomalies detected. System nominal.
          </div>
        ) : (
          events.map((event, i) => (
            <div
              key={`${event.incident_id}-${i}`}
              className={`flex items-start gap-3 p-2 rounded-lg border text-xs animate-slide-up ${getSeverityColor(event.severity)}`}
            >
              <span className="shrink-0 text-slate-500 tabular-nums">
                {formatTime(event.detected_at)}
              </span>
              <div className="flex-1 min-w-0">
                <span className="font-semibold">{event.service}</span>
                <span className="text-slate-400 mx-1">›</span>
                <span className="text-slate-300">{event.metric_name}</span>
                <span className="text-slate-400 mx-1">·</span>
                <span>{formatValue(event)}</span>
                <span className="ml-2 text-slate-500">
                  ({event.deviation_sigma.toFixed(1)}σ deviation)
                </span>
              </div>
              <span className={`shrink-0 px-1.5 py-0.5 rounded text-[10px] uppercase font-bold
                ${event.severity === 'critical' ? 'bg-red-500/20 text-red-300' : 'bg-yellow-500/20 text-yellow-300'}`}>
                {event.severity}
              </span>
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
};

export default AnomalyFeed;
