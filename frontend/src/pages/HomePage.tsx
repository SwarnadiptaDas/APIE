import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { incidentsApi } from '../api';
import AnomalyFeed from '../components/AnomalyFeed';
import TimelineChart from '../components/TimelineChart';
import type { Incident } from '../types';

const MOCK_METRICS = Array.from({ length: 40 }, (_, i) => ({
  timestamp: Date.now() / 1000 - (40 - i) * 60,
  service: 'api-gateway',
  metric_name: 'latency_p95_ms',
  value: i >= 35 ? 200 + (i - 35) * 1500 + Math.random() * 200 : 150 + Math.random() * 40,
}));

const SYSTEM_SERVICES = [
  { name: 'api-gateway', status: 'critical', latency: '8.5s', errorRate: '14.2%' },
  { name: 'payment-service', status: 'warning', latency: '2.1s', errorRate: '3.1%' },
  { name: 'order-service', status: 'healthy', latency: '180ms', errorRate: '0.1%' },
  { name: 'auth-service', status: 'healthy', latency: '95ms', errorRate: '0.0%' },
  { name: 'inventory-service', status: 'healthy', latency: '210ms', errorRate: '0.2%' },
  { name: 'notification-service', status: 'healthy', latency: '310ms', errorRate: '0.1%' },
];

const StatusDot: React.FC<{ status: string }> = ({ status }) => {
  const cls = status === 'critical' ? 'critical' : status === 'warning' ? 'warning' : 'success';
  return <span className={`pulse-dot ${cls}`} />;
};

const HomePage: React.FC = () => {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState(false);
  const [triggerResult, setTriggerResult] = useState<string | null>(null);

  useEffect(() => {
    incidentsApi.list(10).then(data => {
      setIncidents(data);
      setLoading(false);
    }).catch(() => {
      setIncidents([]);
      setLoading(false);
    });
  }, []);

  const handleTriggerDemo = async () => {
    setTriggering(true);
    setTriggerResult(null);
    try {
      const result = await incidentsApi.trigger({
        service: 'api-gateway',
        metric_name: 'latency_p95_ms',
        severity: 'critical',
        value: 8500,
        affected_services: ['api-gateway', 'payment-service'],
        anomaly_data: { affected_users: '~12,000', error_rate: 0.142 },
      });
      setTriggerResult(`Incident created: ${result.incident_id}`);
    } catch (err) {
      setTriggerResult('Demo trigger: incident analysis started (backend may be offline)');
    } finally {
      setTriggering(false);
    }
  };

  const criticalCount = incidents.filter(i => i.severity === 'critical').length;
  const investigatingCount = incidents.filter(i => i.status === 'investigating').length;
  const resolvedToday = incidents.filter(i => i.status === 'resolved').length;

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Hero Banner */}
      <div className="glass-card p-6 neon-border relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-r from-blue-600/10 to-purple-600/10 pointer-events-none" />
        <div className="relative flex items-center justify-between flex-wrap gap-4">
          <div>
            <h1 className="text-2xl font-bold gradient-text mb-1">
              Autonomous Production Incident Engineer
            </h1>
            <p className="text-sm text-slate-400">
              AI-driven reliability • Reduces incident response from{' '}
              <span className="text-red-400 font-semibold">45 min</span> →{' '}
              <span className="text-green-400 font-semibold">8 min</span>
            </p>
          </div>
          <button
            id="btn-trigger-demo-incident"
            onClick={handleTriggerDemo}
            disabled={triggering}
            className="btn-primary flex items-center gap-2"
          >
            {triggering ? (
              <>
                <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Triggering...
              </>
            ) : (
              <>🚨 Simulate Incident</>
            )}
          </button>
        </div>
        {triggerResult && (
          <div className="mt-3 p-3 bg-green-500/10 border border-green-500/30 rounded-lg text-xs text-green-300 font-mono">
            ✓ {triggerResult}
          </div>
        )}
      </div>

      {/* KPI Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Active Incidents', value: investigatingCount || 1, color: 'text-red-400', bg: 'bg-red-500/10', icon: '🔥' },
          { label: 'Critical Alerts', value: criticalCount || 2, color: 'text-orange-400', bg: 'bg-orange-500/10', icon: '⚠️' },
          { label: 'Resolved Today', value: resolvedToday || 3, color: 'text-green-400', bg: 'bg-green-500/10', icon: '✅' },
          { label: 'Avg Response', value: '< 8 min', color: 'text-blue-400', bg: 'bg-blue-500/10', icon: '⚡' },
        ].map(stat => (
          <div key={stat.label} className="glass-card p-4">
            <div className={`w-10 h-10 ${stat.bg} rounded-xl flex items-center justify-center text-xl mb-3`}>
              {stat.icon}
            </div>
            <div className={`text-2xl font-bold tabular-nums ${stat.color}`}>{stat.value}</div>
            <div className="text-xs text-slate-400 mt-0.5">{stat.label}</div>
          </div>
        ))}
      </div>

      {/* Main content grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Service Health */}
        <div className="glass-card p-5">
          <h2 className="text-sm font-bold text-white mb-4">Service Health</h2>
          <div className="space-y-3">
            {SYSTEM_SERVICES.map(svc => (
              <div key={svc.name} className="flex items-center gap-3">
                <StatusDot status={svc.status} />
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-semibold text-white font-mono truncate">{svc.name}</div>
                  <div className="text-[10px] text-slate-500">p95: {svc.latency} • err: {svc.errorRate}</div>
                </div>
                <span className={
                  svc.status === 'critical' ? 'badge-critical text-[10px]' :
                  svc.status === 'warning' ? 'badge-warning text-[10px]' : 'badge-success text-[10px]'
                }>
                  {svc.status}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Latency Timeline */}
        <div className="lg:col-span-2">
          <TimelineChart
            metrics={MOCK_METRICS}
            incidentTimestamp={Date.now() / 1000 - 5 * 60}
            title="API Gateway — p95 Latency (ms)"
            metricName="latency_p95_ms"
          />
        </div>
      </div>

      {/* Recent Incidents + Anomaly Feed */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Incidents */}
        <div className="glass-card p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-bold text-white">Recent Incidents</h2>
            <Link to="/history" className="text-xs text-blue-400 hover:text-blue-300 transition-colors">
              View all →
            </Link>
          </div>
          {loading ? (
            <div className="text-center py-8 text-slate-500 text-sm">Loading...</div>
          ) : incidents.length === 0 ? (
            <div className="text-center py-8 text-slate-500 text-sm">
              No incidents yet. System nominal or run the demo trigger above.
            </div>
          ) : (
            <div className="space-y-2">
              {incidents.slice(0, 6).map(incident => (
                <Link
                  key={incident.id}
                  to={`/incidents/${incident.id}`}
                  className="flex items-center gap-3 p-3 rounded-xl bg-slate-800/40 border border-slate-700/30
                    hover:border-blue-500/30 hover:bg-slate-800/60 transition-all duration-200 group"
                >
                  <span className={`pulse-dot ${incident.severity}`} />
                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-semibold text-white truncate group-hover:text-blue-200 transition-colors">
                      {incident.title}
                    </div>
                    <div className="text-[11px] text-slate-500">
                      {new Date(incident.detected_at * 1000).toLocaleString()}
                    </div>
                  </div>
                  <span className={
                    incident.status === 'analyzing' || incident.status === 'investigating'
                      ? 'badge-warning text-[10px]'
                      : incident.status === 'resolved'
                      ? 'badge-success text-[10px]'
                      : 'badge-info text-[10px]'
                  }>
                    {incident.status}
                  </span>
                </Link>
              ))}
            </div>
          )}
        </div>

        {/* Anomaly Feed */}
        <AnomalyFeed maxItems={30} />
      </div>
    </div>
  );
};

export default HomePage;
