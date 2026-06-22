// ─── Types for the Incident Engineering Platform ─────────────────────────────

export type Severity = 'critical' | 'warning' | 'info';
export type IncidentStatus = 'investigating' | 'analyzed' | 'auto_remediated' | 'failed' | 'resolved';

export interface MetricAnomaly {
  metric: string;
  service: string;
  current_value: number;
  baseline_value: number;
  deviation_sigma: number;
}

export interface ErrorLog {
  timestamp: string | number;
  service: string;
  level: string;
  message: string;
  trace_id?: string;
  count?: number;
}

export interface ErrorTrace {
  trace_id: string;
  service: string;
  operation: string;
  duration_ms: number;
  error: string;
}

export interface CorrelatedEvidence {
  summary: string;
  error_logs: ErrorLog[];
  error_traces: ErrorTrace[];
  metric_anomalies: MetricAnomaly[];
  affected_services: string[];
  key_observations: string[];
  incident_window_start?: string;
  incident_window_end?: string;
}

export interface ValidationChecks {
  log_pattern_match: boolean;
  trace_timing_align: boolean;
  metric_anomaly_support: boolean;
}

export interface Hypothesis {
  rank: number;
  hypothesis_text: string;
  root_cause_category: string;
  supporting_evidence: string[];
  suggested_fix: string;
  confidence_score?: number;
  final_confidence_score?: number;
  original_confidence?: number;
  confidence_adjustment?: number;
  validation_checks?: ValidationChecks;
  validation_reasoning?: string;
}

export interface SimilarIncident {
  incident_id: string;
  title: string;
  root_cause: string;
  corrective_actions: string;
  resolution_minutes: number;
  similarity_score: number;
}

export interface ImpactSummary {
  affected_users: string | number;
  duration_minutes: number;
  error_rate: number;
  affected_services: string[];
}

export interface IncidentTimeline {
  detected: string;
  investigation_started: string;
  root_cause_identified: string;
  resolved: string;
}

export interface AgentTimelineEntry {
  agent: string;
  action: string;
  timestamp: string;
}

export interface AnalysisResult {
  incident_id: string;
  title: string;
  severity: Severity;
  status: IncidentStatus;
  detected_at: string;
  analyzed_at?: string;
  timeline: IncidentTimeline;
  root_cause_summary: string;
  root_cause_category: string;
  confidence_score: number;
  impact: ImpactSummary;
  hypotheses: Hypothesis[];
  corrective_actions: string[];
  preventions: string[];
  supporting_evidence: {
    logs: ErrorLog[];
    traces: ErrorTrace[];
    metrics: MetricAnomaly[];
  };
  similar_incidents: SimilarIncident[];
  postmortem: string;
  auto_remediation?: {
    attempted: boolean;
    success: boolean;
    action_id?: string;
    output?: string;
  };
  agent_timeline: AgentTimelineEntry[];
}

export interface Incident {
  id: string;
  title: string;
  status: IncidentStatus;
  severity: Severity;
  detected_at: number;
  resolved_at?: number;
  affected_services: string[];
  anomaly_data: Record<string, unknown>;
  analysis_result: Partial<AnalysisResult>;
  postmortem: string;
}

export interface AnomalyEvent {
  event_type: string;
  incident_id: string;
  service: string;
  metric_name: string;
  severity: Severity;
  value: number;
  baseline: number;
  deviation_sigma: number;
  timestamp: number;
  detected_at: number;
}

export interface MetricDataPoint {
  timestamp: number;
  service: string;
  metric_name: string;
  value: number;
}

export interface ActionResult {
  success: boolean;
  action_id: string;
  incident_id: string;
  output: string;
  simulated?: boolean;
  error?: string;
  timestamp: number;
}

export interface WsMessage {
  event: 'incident_created' | 'analysis_complete' | 'action_executed' | 'incident_resolved' | 'analysis_failed' | 'initial_state' | 'ping';
  incident?: Incident;
  incident_id?: string;
  result?: AnalysisResult | ActionResult;
  incidents?: Incident[];
  error?: string;
  timestamp?: number;
}
