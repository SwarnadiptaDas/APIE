import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { incidentsApi } from '../api';
import RootCauseCard from '../components/RootCauseCard';
import HypothesisPanel from '../components/HypothesisPanel';
import TimelineChart from '../components/TimelineChart';
import PostmortemViewer from '../components/PostmortemViewer';
import ActionButton from '../components/ActionButton';
import type { Incident, AnalysisResult, Hypothesis } from '../types';

const AgentTimeline: React.FC<{ timeline: Array<{ agent: string; action: string; timestamp: string }> }> = ({ timeline }) => (
  <div className="glass-card p-5">
    <h3 className="text-sm font-bold text-white mb-4">AI Agent Pipeline</h3>
    <div className="timeline-line space-y-4">
      {(['investigator', 'hypothesis', 'validator', 'reporter', 'remediator'] as const).map((agent, i) => {
        const entry = timeline.find(t => t.agent === agent);
        const done = !!entry;
        const agentLabels = {
          investigator: { label: 'Investigator Agent', desc: 'Correlating logs, traces, metrics', icon: '🔍' },
          hypothesis: { label: 'Hypothesis Agent', desc: 'Generating root cause theories', icon: '🧪' },
          validator: { label: 'Validator Agent', desc: 'Scoring confidence levels', icon: '⚖️' },
          reporter: { label: 'Reporter Agent', desc: 'Generating postmortem document', icon: '📝' },
          remediator: { label: 'Remediator Agent', desc: 'Autonomously executing fixes', icon: '🤖' },
        };
        const info = agentLabels[agent];

        return (
          <div key={agent} className="flex items-start gap-4">
            <div className={`w-10 h-10 rounded-xl flex items-center justify-center text-lg shrink-0 z-10 transition-all duration-500
              ${done
                ? 'bg-blue-500/20 border border-blue-500/40 shadow-lg shadow-blue-500/20'
                : 'bg-slate-800/50 border border-slate-700/30 opacity-40'}`}>
              {info.icon}
            </div>
            <div className="flex-1 min-w-0 pt-1">
              <div className="flex items-center gap-2">
                <span className={`text-sm font-semibold ${done ? 'text-white' : 'text-slate-500'}`}>
                  {info.label}
                </span>
                {done && <span className="badge-success text-[10px]">✓ Done</span>}
                {!done && <span className="text-[10px] text-slate-600">Pending</span>}
              </div>
              <div className={`text-xs mt-0.5 ${done ? 'text-slate-400' : 'text-slate-600'}`}>
                {done ? entry.action.replace(/_/g, ' ') : info.desc}
              </div>
              {done && (
                <div className="text-[10px] text-slate-600 font-mono mt-0.5">
                  {new Date(entry.timestamp).toLocaleTimeString()}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  </div>
);

const IncidentPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const [incident, setIncident] = useState<Incident | null>(null);
  const [loading, setLoading] = useState(true);
  const [resolving, setResolving] = useState(false);

  useEffect(() => {
    if (!id) return;
    const fetchIncident = async () => {
      try {
        const data = await incidentsApi.get(id);
        setIncident(data);
      } catch {
        // Use mock data if backend offline
        setIncident(createMockIncident(id));
      } finally {
        setLoading(false);
      }
    };
    fetchIncident();

    // Poll for updates if still investigating
    const interval = setInterval(async () => {
      try {
        const data = await incidentsApi.get(id);
        setIncident(data);
        if (data.status === 'analyzed' || data.status === 'resolved') {
          clearInterval(interval);
        }
      } catch { /* ignore */ }
    }, 5000);

    return () => clearInterval(interval);
  }, [id]);

  const handleResolve = async () => {
    if (!id) return;
    setResolving(true);
    try {
      await incidentsApi.resolve(id);
      setIncident(prev => prev ? { ...prev, status: 'resolved' } : null);
    } catch (err) {
      console.error(err);
    } finally {
      setResolving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-10 h-10 border-2 border-blue-500/30 border-t-blue-500 rounded-full animate-spin" />
      </div>
    );
  }

  if (!incident) {
    return (
      <div className="text-center py-16">
        <div className="text-4xl mb-4">🔍</div>
        <div className="text-white font-semibold">Incident not found</div>
        <Link to="/" className="text-blue-400 text-sm mt-2 block">← Back to dashboard</Link>
      </div>
    );
  }

  const analysis = incident.analysis_result as Partial<AnalysisResult>;
  const hypotheses = analysis?.hypotheses || [];
  const topH = hypotheses[0] as Hypothesis | undefined;
  const agentTimeline = analysis?.agent_timeline || [];

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Breadcrumb + Actions */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2 text-sm">
          <Link to="/" className="text-slate-400 hover:text-white transition-colors">Dashboard</Link>
          <span className="text-slate-600">›</span>
          <Link to="/history" className="text-slate-400 hover:text-white transition-colors">Incidents</Link>
          <span className="text-slate-600">›</span>
          <span className="text-white font-mono text-xs">{incident.id.slice(0, 12)}...</span>
        </div>

        {incident.status !== 'resolved' && (
          <button
            id={`btn-resolve-incident-${id}`}
            onClick={handleResolve}
            disabled={resolving}
            className="btn-ghost text-xs"
          >
            {resolving ? 'Resolving...' : '✓ Mark Resolved'}
          </button>
        )}
      </div>

      {/* Incident Header */}
      <div className="glass-card p-5">
        <div className="flex items-start gap-4 flex-wrap">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-3 mb-2 flex-wrap">
              <span className={incident.severity === 'critical' ? 'badge-critical' : 'badge-warning'}>
                {incident.severity}
              </span>
              <span className={
                incident.status === 'analyzed' ? 'badge-success' :
                incident.status === 'auto_remediated' ? 'badge-info' :
                incident.status === 'resolved' ? 'badge-info' :
                incident.status === 'failed' ? 'badge-critical' : 'badge-warning'
              }>
                {incident.status}
              </span>
            </div>
            <h1 className="text-xl font-bold text-white mb-2">{incident.title}</h1>
            <div className="flex items-center gap-4 text-xs text-slate-400 flex-wrap">
              <span>🕐 Detected: {new Date(incident.detected_at * 1000).toLocaleString()}</span>
              <span>🎯 Services: {incident.affected_services.join(', ')}</span>
              {analysis?.confidence_score && (
                <span>📊 Confidence: <span className="text-green-400 font-semibold">{analysis.confidence_score}%</span></span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Root Cause + Agent Timeline */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <RootCauseCard
            hypothesis={topH || null}
            severity={incident.severity}
            status={incident.status}
            incidentId={incident.id}
          />
          {analysis?.auto_remediation?.attempted && (
            <div className={`glass-card p-5 border-2 ${analysis.auto_remediation.success ? 'border-green-500/40 bg-green-500/5' : 'border-red-500/40 bg-red-500/5'}`}>
              <div className="flex items-center gap-2 mb-3">
                <span className="text-xl">🤖</span>
                <h3 className="text-sm font-bold text-white">Autonomous Remediation</h3>
                <span className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded-full ${analysis.auto_remediation.success ? 'bg-green-500/20 text-green-300' : 'bg-red-500/20 text-red-300'}`}>
                  {analysis.auto_remediation.success ? 'Success' : 'Failed'}
                </span>
              </div>
              <p className="text-xs text-slate-300 mb-2">
                The Remediator Agent executed action: <span className="font-mono text-blue-300">{analysis.auto_remediation.action_id || 'unknown'}</span>
              </p>
              <div className="code-block text-slate-300">
                {analysis.auto_remediation.output}
              </div>
            </div>
          )}
        </div>
        <AgentTimeline timeline={agentTimeline} />
      </div>

      {/* Metric Charts */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <TimelineChart
          metrics={[]}
          incidentTimestamp={incident.detected_at}
          title="p95 Latency (ms)"
          metricName="latency_p95_ms"
        />
        <TimelineChart
          metrics={[]}
          incidentTimestamp={incident.detected_at}
          title="Error Rate"
          metricName="error_rate"
        />
      </div>

      {/* Hypotheses */}
      <HypothesisPanel hypotheses={hypotheses} topHypothesisIndex={0} />

      {/* Actions + Postmortem */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ActionButton
          incidentId={incident.id}
          affectedService={incident.affected_services[0]}
        />
        <PostmortemViewer
          postmortem={incident.postmortem || analysis?.postmortem || ''}
          incidentId={incident.id}
        />
      </div>

      {/* Similar Incidents */}
      {analysis?.similar_incidents && analysis.similar_incidents.length > 0 && (
        <div className="glass-card p-5">
          <h3 className="text-sm font-bold text-white mb-4">Similar Historical Incidents (RAG)</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {analysis.similar_incidents.map((sim, i) => (
              <div key={i} className="p-3 bg-slate-800/40 border border-slate-700/30 rounded-xl text-xs">
                <div className="font-semibold text-white mb-1 truncate">{sim.title}</div>
                <div className="text-slate-400 mb-2">{sim.root_cause}</div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">
                    ⏱ {sim.resolution_minutes}m resolution
                  </span>
                  <span className="text-blue-400 font-semibold">
                    {Math.round(sim.similarity_score * 100)}% match
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

function createMockIncident(id: string): Incident {
  return {
    id,
    title: 'Production Outage: API Latency Spike — api-gateway',
    status: 'analyzed',
    severity: 'critical',
    detected_at: Date.now() / 1000 - 1200,
    affected_services: ['api-gateway', 'payment-service'],
    anomaly_data: { service: 'api-gateway', metric_name: 'latency_p95_ms', value: 8500 },
    analysis_result: {
      confidence_score: 87,
      root_cause_summary: 'Database connection pool exhausted causing API latency spike',
      hypotheses: [
        {
          rank: 1,
          hypothesis_text: 'Database connection pool exhausted causing cascading timeout',
          root_cause_category: 'connection_pool',
          supporting_evidence: [
            'ERROR: connection pool exhausted (50/50 connections used)',
            'Trace span: db.query p95=6.2s (baseline 80ms)',
            'Metric: error_rate spiked from 0.1% to 14.2%',
          ],
          suggested_fix: 'Increase connection pool size from 50 to 100 and add connection timeout of 5s',
          final_confidence_score: 87,
          original_confidence: 70,
          confidence_adjustment: 17,
          validation_checks: {
            log_pattern_match: true,
            trace_timing_align: true,
            metric_anomaly_support: true,
          },
          validation_reasoning: '3/3 validation checks passed — strong evidence alignment',
        },
        {
          rank: 2,
          hypothesis_text: 'Memory leak in payment-service causing OOM GC pauses',
          root_cause_category: 'memory_leak',
          supporting_evidence: ['Memory usage: 89% (baseline 55%)', 'GC pause events detected'],
          suggested_fix: 'Restart payment-service and investigate memory allocation patterns',
          final_confidence_score: 52,
          original_confidence: 55,
          confidence_adjustment: -3,
          validation_checks: { log_pattern_match: false, trace_timing_align: true, metric_anomaly_support: true },
          validation_reasoning: '2/3 validation checks passed',
        },
        {
          rank: 3,
          hypothesis_text: 'Sudden traffic spike overwhelming thread pool',
          root_cause_category: 'thread_pool',
          supporting_evidence: ['Request volume: 3.2x normal', 'Queue depth: 2400 requests'],
          suggested_fix: 'Scale up api-gateway to 10 replicas immediately',
          final_confidence_score: 38,
          original_confidence: 40,
          confidence_adjustment: -2,
          validation_checks: { log_pattern_match: false, trace_timing_align: false, metric_anomaly_support: true },
          validation_reasoning: '1/3 validation checks passed',
        },
      ],
      agent_timeline: [
        { agent: 'investigator', action: 'evidence_correlated', timestamp: new Date(Date.now() - 600000).toISOString() },
        { agent: 'hypothesis', action: 'generated_3_hypotheses', timestamp: new Date(Date.now() - 480000).toISOString() },
        { agent: 'validator', action: 'confidence=87%', timestamp: new Date(Date.now() - 360000).toISOString() },
        { agent: 'reporter', action: 'postmortem_generated', timestamp: new Date(Date.now() - 240000).toISOString() },
      ],
      similar_incidents: [
        {
          incident_id: 'hist-001',
          title: 'DB Connection Pool Exhaustion — Feb 2024',
          root_cause: 'Connection pool size 30 insufficient for traffic',
          corrective_actions: 'Increased pool to 100',
          resolution_minutes: 12,
          similarity_score: 0.91,
        },
      ],
    } as Partial<AnalysisResult>,
    postmortem: `====== INCIDENT POSTMORTEM ======

## Title: Production Outage — API Latency Spike (DB Connection Pool Exhaustion)

**Date:** ${new Date().toLocaleDateString()}  
**Status:** Resolved  
**Severity:** CRITICAL  

## Executive Summary

A production outage affecting ~12,000 users was caused by database connection pool exhaustion in the \`api-gateway\` service. The AI Incident Agent identified the root cause within 4 minutes and recommended increasing the connection pool size from 50 to 100. Service recovered within 8 minutes of detection.

## Timeline

- **T+0:00** — Anomaly detected: \`latency_p95_ms\` spiked to 8,500ms (baseline 200ms)
- **T+0:15** — AI investigation initiated (Investigator Agent)
- **T+1:30** — 3 hypotheses generated (Hypothesis Agent)
- **T+2:45** — Root cause validated with 87% confidence (Validator Agent)
- **T+4:00** — Postmortem generated, corrective action recommended
- **T+8:00** — Connection pool increased, service recovered

## Impact

- **Affected Users:** ~12,000
- **Duration:** 8 minutes  
- **Peak Error Rate:** 14.2%  
- **Services Affected:** api-gateway, payment-service

## Root Cause

**Primary**: Database connection pool exhausted (50/50 connections held)

All 50 connections were held by long-running transactions, preventing new requests from obtaining connections. This caused a queue buildup of 2,400 requests and p95 latency to spike to 8.5 seconds.

## Corrective Actions

1. Increased DB connection pool size from 50 → 100
2. Restarted payment-service to release held connections
3. Added connection timeout of 5 seconds

## Prevention Recommendations

1. **Immediate**: Add connection pool monitoring alert at 80% utilization
2. **Short-term**: Implement circuit breaker pattern on DB calls
3. **Long-term**: Connection pool auto-scaling based on traffic patterns

**AI Confidence Score:** 87%

====== END POSTMORTEM ======`,
  };
}

export default IncidentPage;
