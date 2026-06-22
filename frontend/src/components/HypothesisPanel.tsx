import React, { useState } from 'react';
import type { Hypothesis } from '../types';

interface HypothesisPanelProps {
  hypotheses: Hypothesis[];
  topHypothesisIndex?: number;
}

const categoryIcons: Record<string, string> = {
  connection_pool: '🔗',
  memory_leak: '💾',
  network_timeout: '🌐',
  cache: '⚡',
  thread_pool: '🔄',
  cpu: '🖥️',
  cascading: '🌊',
  config: '⚙️',
  resource: '📦',
  race_condition: '🏎️',
  unknown: '❓',
};

const categoryLabels: Record<string, string> = {
  connection_pool: 'Connection Pool',
  memory_leak: 'Memory Leak',
  network_timeout: 'Network Timeout',
  cache: 'Cache Issue',
  thread_pool: 'Thread Pool',
  cpu: 'CPU Throttling',
  cascading: 'Cascading Failure',
  config: 'Config Change',
  resource: 'Resource Exhaustion',
  race_condition: 'Race Condition',
  unknown: 'Unknown',
};

const HypothesisPanel: React.FC<HypothesisPanelProps> = ({ hypotheses, topHypothesisIndex = 0 }) => {
  const [expanded, setExpanded] = useState<number | null>(0);

  const getConfidenceColor = (score: number) => {
    if (score >= 75) return { bar: 'bg-green-500', text: 'text-green-400', border: 'border-green-500/30' };
    if (score >= 50) return { bar: 'bg-yellow-500', text: 'text-yellow-400', border: 'border-yellow-500/30' };
    return { bar: 'bg-red-500', text: 'text-red-400', border: 'border-red-500/30' };
  };

  if (!hypotheses || hypotheses.length === 0) {
    return (
      <div className="glass-card p-6">
        <h3 className="text-base font-semibold text-white mb-3">Root Cause Hypotheses</h3>
        <div className="text-center text-slate-500 py-8 text-sm">
          No hypotheses generated yet. Investigation in progress...
        </div>
      </div>
    );
  }

  return (
    <div className="glass-card p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-base font-semibold text-white">Root Cause Hypotheses</h3>
        <span className="text-xs text-slate-400">{hypotheses.length} hypotheses ranked by confidence</span>
      </div>

      <div className="space-y-3">
        {hypotheses.map((h, idx) => {
          const confidence = h.final_confidence_score ?? h.confidence_score ?? 0;
          const colors = getConfidenceColor(confidence);
          const isTop = idx === topHypothesisIndex;
          const isExpanded = expanded === idx;

          return (
            <div
              key={idx}
              className={`rounded-xl border p-4 cursor-pointer transition-all duration-200
                ${isTop
                  ? `border-blue-500/40 bg-blue-500/5 ${isExpanded ? 'ring-1 ring-blue-500/20' : ''}`
                  : `border-slate-700/50 bg-slate-800/30 hover:border-slate-600/50`
                }`}
              onClick={() => setExpanded(isExpanded ? null : idx)}
            >
              {/* Header */}
              <div className="flex items-start gap-3">
                <div className={`shrink-0 w-8 h-8 rounded-lg flex items-center justify-center text-sm font-bold
                  ${isTop ? 'bg-blue-500/20 text-blue-400' : 'bg-slate-700/50 text-slate-400'}`}>
                  #{h.rank ?? idx + 1}
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <span className="text-sm font-semibold text-white leading-tight">
                      {h.hypothesis_text}
                    </span>
                    {isTop && (
                      <span className="shrink-0 px-2 py-0.5 bg-blue-500/20 text-blue-300 text-[10px] rounded-full font-bold uppercase">
                        Top Candidate
                      </span>
                    )}
                  </div>

                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-[11px] text-slate-400">
                      {categoryIcons[h.root_cause_category ?? 'unknown']} {categoryLabels[h.root_cause_category ?? 'unknown']}
                    </span>
                    {h.confidence_adjustment !== undefined && (
                      <span className={`text-[11px] font-mono
                        ${h.confidence_adjustment >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {h.confidence_adjustment >= 0 ? '+' : ''}{h.confidence_adjustment} adj
                      </span>
                    )}
                  </div>
                </div>

                <div className="shrink-0 text-right">
                  <div className={`text-lg font-bold tabular-nums ${colors.text}`}>
                    {confidence}%
                  </div>
                  <div className="text-[10px] text-slate-500">confidence</div>
                </div>
              </div>

              {/* Confidence bar */}
              <div className="mt-3 confidence-bar">
                <div
                  className={`confidence-fill ${colors.bar}`}
                  style={{ width: `${confidence}%` }}
                />
              </div>

              {/* Expanded: validation + evidence + fix */}
              {isExpanded && (
                <div className="mt-4 space-y-3 animate-fade-in">
                  {/* Validation checks */}
                  {h.validation_checks && (
                    <div>
                      <div className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">
                        Validation Checks
                      </div>
                      <div className="grid grid-cols-3 gap-2">
                        {Object.entries(h.validation_checks).map(([key, passed]) => (
                          <div
                            key={key}
                            className={`flex items-center gap-1.5 p-2 rounded-lg text-[11px]
                              ${passed
                                ? 'bg-green-500/10 border border-green-500/20 text-green-400'
                                : 'bg-red-500/10 border border-red-500/20 text-red-400'}`}
                          >
                            <span>{passed ? '✓' : '✗'}</span>
                            <span className="truncate">{key.replace(/_/g, ' ')}</span>
                          </div>
                        ))}
                      </div>
                      {h.validation_reasoning && (
                        <p className="text-[11px] text-slate-500 mt-2 italic">{h.validation_reasoning}</p>
                      )}
                    </div>
                  )}

                  {/* Supporting evidence */}
                  {h.supporting_evidence && h.supporting_evidence.length > 0 && (
                    <div>
                      <div className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">
                        Supporting Evidence
                      </div>
                      <ul className="space-y-1">
                        {h.supporting_evidence.slice(0, 4).map((e, i) => (
                          <li key={i} className="text-xs text-slate-300 flex items-start gap-2">
                            <span className="text-blue-400 shrink-0 mt-0.5">›</span>
                            <span className="break-words">{e}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Suggested fix */}
                  {h.suggested_fix && (
                    <div className="p-3 bg-green-500/5 border border-green-500/20 rounded-lg">
                      <div className="text-xs font-semibold text-green-400 mb-1 uppercase tracking-wide">
                        Suggested Fix
                      </div>
                      <p className="text-xs text-green-300">{h.suggested_fix}</p>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default HypothesisPanel;
