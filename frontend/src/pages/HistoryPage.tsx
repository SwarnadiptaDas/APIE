import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { incidentsApi } from '../api';
import type { Incident, Severity, IncidentStatus } from '../types';

const HistoryPage: React.FC = () => {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [severityFilter, setSeverityFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<string>('all');

  useEffect(() => {
    incidentsApi.list(100).then(data => {
      setIncidents(data);
      setLoading(false);
    }).catch(() => {
      // Show mock data when backend offline
      setIncidents(MOCK_INCIDENTS);
      setLoading(false);
    });
  }, []);

  const filtered = incidents.filter(inc => {
    const matchesSearch = !search || 
      inc.title.toLowerCase().includes(search.toLowerCase()) ||
      inc.affected_services.some(s => s.toLowerCase().includes(search.toLowerCase()));
    const matchesSeverity = severityFilter === 'all' || inc.severity === severityFilter;
    const matchesStatus = statusFilter === 'all' || inc.status === statusFilter;
    return matchesSearch && matchesSeverity && matchesStatus;
  });

  const stats = {
    total: incidents.length,
    critical: incidents.filter(i => i.severity === 'critical').length,
    resolved: incidents.filter(i => i.status === 'resolved').length,
    avgResolution: '8 min',
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold text-white mb-1">Incident History</h1>
        <p className="text-sm text-slate-400">Searchable log of all production incidents analyzed by the AI system</p>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Total Incidents', value: stats.total, color: 'text-white' },
          { label: 'Critical', value: stats.critical, color: 'text-red-400' },
          { label: 'Resolved', value: stats.resolved, color: 'text-green-400' },
          { label: 'Avg Resolution', value: stats.avgResolution, color: 'text-blue-400' },
        ].map(s => (
          <div key={s.label} className="glass-card p-4 text-center">
            <div className={`text-2xl font-bold ${s.color}`}>{s.value}</div>
            <div className="text-xs text-slate-400 mt-1">{s.label}</div>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="glass-card p-4 flex flex-wrap gap-3 items-center">
        <input
          id="input-search-incidents"
          type="text"
          placeholder="Search incidents or services..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="flex-1 min-w-48 bg-slate-800/50 border border-slate-700/50 rounded-xl px-4 py-2.5 text-sm
            text-white placeholder-slate-500 focus:outline-none focus:border-blue-500/50 transition-colors"
        />
        <select
          id="select-severity-filter"
          value={severityFilter}
          onChange={e => setSeverityFilter(e.target.value)}
          className="bg-slate-800/50 border border-slate-700/50 rounded-xl px-3 py-2.5 text-sm text-white
            focus:outline-none focus:border-blue-500/50 transition-colors"
        >
          <option value="all">All Severities</option>
          <option value="critical">Critical</option>
          <option value="warning">Warning</option>
          <option value="info">Info</option>
        </select>
        <select
          id="select-status-filter"
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
          className="bg-slate-800/50 border border-slate-700/50 rounded-xl px-3 py-2.5 text-sm text-white
            focus:outline-none focus:border-blue-500/50 transition-colors"
        >
          <option value="all">All Statuses</option>
          <option value="investigating">Investigating</option>
          <option value="analyzed">Analyzed</option>
          <option value="resolved">Resolved</option>
          <option value="failed">Failed</option>
        </select>
        <span className="text-xs text-slate-400 ml-auto">
          {filtered.length} of {incidents.length} incidents
        </span>
      </div>

      {/* Incident Table */}
      {loading ? (
        <div className="flex justify-center py-16">
          <div className="w-8 h-8 border-2 border-blue-500/30 border-t-blue-500 rounded-full animate-spin" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="glass-card p-12 text-center">
          <div className="text-4xl mb-3">🔍</div>
          <div className="text-white font-semibold mb-1">No incidents found</div>
          <div className="text-sm text-slate-400">Try adjusting your search or filters</div>
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map(incident => {
            const confidence = (incident.analysis_result as { confidence_score?: number })?.confidence_score;
            const duration = incident.resolved_at
              ? Math.round((incident.resolved_at - incident.detected_at) / 60)
              : null;

            return (
              <Link
                key={incident.id}
                to={`/incidents/${incident.id}`}
                className="glass-card p-4 flex items-center gap-4 hover:neon-border transition-all duration-200 group cursor-pointer"
                style={{ display: 'flex' }}
              >
                {/* Severity indicator */}
                <div className={`w-1.5 h-12 rounded-full shrink-0
                  ${incident.severity === 'critical' ? 'bg-red-500' :
                    incident.severity === 'warning' ? 'bg-yellow-500' : 'bg-blue-500'}`}
                />

                {/* Main info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className={incident.severity === 'critical' ? 'badge-critical text-[10px]' : 'badge-warning text-[10px]'}>
                      {incident.severity}
                    </span>
                    <span className="text-sm font-semibold text-white truncate group-hover:text-blue-200 transition-colors">
                      {incident.title}
                    </span>
                  </div>
                  <div className="text-xs text-slate-500 mt-0.5 font-mono">
                    {incident.affected_services.join(' • ')}
                  </div>
                </div>

                {/* Metadata */}
                <div className="shrink-0 text-right space-y-1">
                  <div className="text-xs text-slate-400">
                    {new Date(incident.detected_at * 1000).toLocaleDateString()}
                  </div>
                  {confidence !== undefined && (
                    <div className="text-xs font-semibold text-blue-400">{confidence}% confidence</div>
                  )}
                  {duration !== null && (
                    <div className="text-[11px] text-slate-500">⏱ {duration}m</div>
                  )}
                </div>

                {/* Status */}
                <div className="shrink-0">
                  <span className={
                    incident.status === 'resolved' ? 'badge-success text-[10px]' :
                    incident.status === 'analyzed' ? 'badge-info text-[10px]' :
                    incident.status === 'failed' ? 'badge-critical text-[10px]' : 'badge-warning text-[10px]'
                  }>
                    {incident.status}
                  </span>
                </div>

                <span className="text-slate-500 group-hover:text-blue-400 transition-colors text-lg">›</span>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
};

const MOCK_INCIDENTS: Incident[] = [
  {
    id: 'demo-001',
    title: 'Production Outage: API Latency Spike — api-gateway',
    status: 'resolved',
    severity: 'critical',
    detected_at: Date.now() / 1000 - 7200,
    resolved_at: Date.now() / 1000 - 6720,
    affected_services: ['api-gateway', 'payment-service'],
    anomaly_data: {},
    analysis_result: { confidence_score: 87 } as any,
    postmortem: 'Resolved. Root cause: DB connection pool exhausted.',
  },
  {
    id: 'demo-002',
    title: 'Warning: Memory Usage Elevated — payment-service',
    status: 'analyzed',
    severity: 'warning',
    detected_at: Date.now() / 1000 - 3600,
    affected_services: ['payment-service'],
    anomaly_data: {},
    analysis_result: { confidence_score: 72 } as any,
    postmortem: '',
  },
  {
    id: 'demo-003',
    title: 'Warning: Error Rate Spike — order-service',
    status: 'investigating',
    severity: 'warning',
    detected_at: Date.now() / 1000 - 900,
    affected_services: ['order-service', 'inventory-service'],
    anomaly_data: {},
    analysis_result: {},
    postmortem: '',
  },
];

export default HistoryPage;
