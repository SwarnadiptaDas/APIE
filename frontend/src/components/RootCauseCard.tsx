import React from 'react';
import type { Hypothesis, IncidentStatus, Severity } from '../types';

interface RootCauseCardProps {
  hypothesis: Hypothesis | null;
  severity: Severity;
  status: IncidentStatus;
  incidentId: string;
}

const RootCauseCard: React.FC<RootCauseCardProps> = ({
  hypothesis,
  severity,
  status,
  incidentId,
}) => {
  if (!hypothesis || status === 'investigating') {
    return (
      <div className="glass-card p-6 neon-border">
        <div className="flex items-center gap-3 mb-4">
          <div className={`pulse-dot ${severity}`} />
          <h2 className="text-base font-bold text-white">Root Cause Analysis</h2>
          <span className="badge-warning ml-auto">Analyzing...</span>
        </div>
        <div className="flex items-center gap-4 py-4">
          <div className="relative">
            <div className="w-16 h-16 rounded-full border-4 border-blue-500/20" />
            <div
              className="absolute inset-0 w-16 h-16 rounded-full border-4 border-transparent border-t-blue-500 animate-spin"
              style={{ animationDuration: '1.2s' }}
            />
          </div>
          <div>
            <div className="text-sm text-white font-semibold mb-1">AI Agents Investigating...</div>
            <div className="text-xs text-slate-400">
              Correlating logs, traces, and metrics across affected services
            </div>
          </div>
        </div>
        <div className="grid grid-cols-4 gap-2 mt-2">
          {['Investigator', 'Hypothesis', 'Validator', 'Reporter'].map((agent, i) => (
            <div
              key={agent}
              className={`text-center p-2 rounded-lg text-[11px] font-medium transition-all duration-500
                ${i === 0 ? 'bg-blue-500/20 text-blue-300 border border-blue-500/30' : 'bg-slate-800/50 text-slate-500 border border-slate-700/30'}`}
            >
              {agent}
            </div>
          ))}
        </div>
      </div>
    );
  }

  const confidence = hypothesis.final_confidence_score ?? hypothesis.confidence_score ?? 0;

  const getConfidenceGradient = (score: number) => {
    if (score >= 80) return 'from-green-500 to-emerald-400';
    if (score >= 60) return 'from-yellow-500 to-amber-400';
    return 'from-red-500 to-orange-400';
  };

  const getSeverityConfig = (sev: Severity) => {
    switch (sev) {
      case 'critical':
        return { bg: 'bg-red-500/10', border: 'border-red-500/40', text: 'text-red-400', badge: 'badge-critical' };
      case 'warning':
        return { bg: 'bg-yellow-500/10', border: 'border-yellow-500/40', text: 'text-yellow-400', badge: 'badge-warning' };
      default:
        return { bg: 'bg-blue-500/10', border: 'border-blue-500/40', text: 'text-blue-400', badge: 'badge-info' };
    }
  };

  const config = getSeverityConfig(severity);

  return (
    <div className={`glass-card p-6 border-2 ${config.border} ${config.bg} animate-slide-up`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <span className={`pulse-dot ${severity}`} />
          <h2 className="text-base font-bold text-white">Root Cause Identified</h2>
        </div>
        <div className="flex items-center gap-2">
          <span className={config.badge}>{severity}</span>
          <span className={status === 'auto_remediated' ? 'badge-info' : 'badge-success'}>{status.replace('_', '-')}</span>
        </div>
      </div>

      {/* Root Cause Statement */}
      <div className="mb-4">
        <p className="text-lg font-semibold text-white leading-snug">
          {hypothesis.hypothesis_text}
        </p>
        <p className="text-xs text-slate-400 mt-1 font-mono">
          Incident ID: {incidentId.slice(0, 8)}...
        </p>
      </div>

      {/* Confidence Score — radial display */}
      <div className="flex items-center gap-6 mb-4">
        <div className="relative w-20 h-20 shrink-0">
          <svg className="w-20 h-20 -rotate-90" viewBox="0 0 72 72">
            <circle cx="36" cy="36" r="30" fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth="6" />
            <circle
              cx="36" cy="36" r="30"
              fill="none"
              stroke="url(#confGrad)"
              strokeWidth="6"
              strokeLinecap="round"
              strokeDasharray={`${confidence * 1.885} 188.5`}
              style={{ transition: 'stroke-dasharray 1s ease' }}
            />
            <defs>
              <linearGradient id="confGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="#22c55e" />
                <stop offset="100%" stopColor="#3b82f6" />
              </linearGradient>
            </defs>
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-xl font-bold text-white leading-none">{confidence}%</span>
            <span className="text-[10px] text-slate-400">confidence</span>
          </div>
        </div>

        <div className="flex-1">
          {hypothesis.supporting_evidence && hypothesis.supporting_evidence.length > 0 && (
            <div>
              <div className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">Key Evidence</div>
              <ul className="space-y-1.5">
                {hypothesis.supporting_evidence.slice(0, 3).map((e, i) => (
                  <li key={i} className="flex items-start gap-2 text-xs">
                    <span className="text-blue-400 shrink-0">›</span>
                    <span className="text-slate-300 break-words">{e}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>

      {/* Suggested Fix */}
      {hypothesis.suggested_fix && (
        <div className="p-3 bg-green-500/8 border border-green-500/20 rounded-xl">
          <div className="flex items-center gap-2 mb-1.5">
            <span className="text-lg">⚡</span>
            <span className="text-xs font-bold text-green-400 uppercase tracking-wide">
              Recommended Action
            </span>
          </div>
          <p className="text-sm text-green-300">{hypothesis.suggested_fix}</p>
        </div>
      )}
    </div>
  );
};

export default RootCauseCard;
