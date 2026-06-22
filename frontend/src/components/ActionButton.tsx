import React, { useState } from 'react';
import { incidentsApi } from '../api';
import type { ActionResult } from '../types';

interface Action {
  id: string;
  label: string;
  description: string;
  icon: string;
  severity: 'danger' | 'warning' | 'info';
  params?: Record<string, unknown>;
}

const AVAILABLE_ACTIONS: Action[] = [
  {
    id: 'restart_service',
    label: 'Restart Service',
    description: 'kubectl rollout restart the affected deployment',
    icon: '🔄',
    severity: 'warning',
  },
  {
    id: 'scale_up',
    label: 'Scale Up (×2)',
    description: 'Double the replica count to handle increased load',
    icon: '📈',
    severity: 'info',
    params: { replicas: 10 },
  },
  {
    id: 'rollback_deployment',
    label: 'Rollback Deployment',
    description: 'Roll back to the previous stable deployment version',
    icon: '⏪',
    severity: 'danger',
  },
  {
    id: 'flush_cache',
    label: 'Flush Cache',
    description: 'Clear Redis cache to force database reads',
    icon: '🗑️',
    severity: 'warning',
  },
  {
    id: 'increase_pool_size',
    label: 'Increase Connection Pool',
    description: 'Update DB connection pool size from 50 → 100',
    icon: '🔗',
    severity: 'info',
    params: { pool_size: 100 },
  },
];

interface ActionButtonProps {
  incidentId: string;
  affectedService?: string;
}

const ActionButton: React.FC<ActionButtonProps> = ({ incidentId, affectedService }) => {
  const [executing, setExecuting] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, ActionResult>>({});
  const [confirmAction, setConfirmAction] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleExecute = async (action: Action) => {
    if (confirmAction !== action.id) {
      setConfirmAction(action.id);
      return;
    }

    setExecuting(action.id);
    setConfirmAction(null);
    setError(null);

    try {
      const result = await incidentsApi.executeAction(
        incidentId,
        action.id,
        { ...action.params, service: affectedService || 'api-gateway' }
      );
      setResults(prev => ({ ...prev, [action.id]: result }));
    } catch (err) {
      setError(`Action failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setExecuting(null);
    }
  };

  const getSeverityStyle = (severity: string) => {
    switch (severity) {
      case 'danger':
        return 'border-red-500/30 hover:border-red-500/60 hover:bg-red-500/5';
      case 'warning':
        return 'border-yellow-500/30 hover:border-yellow-500/60 hover:bg-yellow-500/5';
      default:
        return 'border-blue-500/30 hover:border-blue-500/60 hover:bg-blue-500/5';
    }
  };

  return (
    <div className="glass-card p-6">
      <h3 className="text-base font-semibold text-white mb-1">One-Click Corrective Actions</h3>
      <p className="text-xs text-slate-400 mb-4">
        Actions execute against {affectedService || 'the affected service'} in your Kubernetes cluster
      </p>

      {error && (
        <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-xs text-red-300">
          {error}
        </div>
      )}

      <div className="space-y-3">
        {AVAILABLE_ACTIONS.map(action => {
          const result = results[action.id];
          const isExecuting = executing === action.id;
          const isConfirming = confirmAction === action.id;
          const isDone = !!result;

          return (
            <div
              key={action.id}
              className={`border rounded-xl p-4 transition-all duration-200 ${getSeverityStyle(action.severity)}`}
              style={{ borderColor: isDone ? 'rgba(34,197,94,0.4)' : undefined }}
            >
              <div className="flex items-center gap-3">
                <span className="text-2xl">{action.icon}</span>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold text-white">{action.label}</div>
                  <div className="text-xs text-slate-400">{action.description}</div>
                </div>

                {isDone ? (
                  <div className={`shrink-0 px-3 py-1.5 rounded-lg text-xs font-bold
                    ${result.success
                      ? 'bg-green-500/20 text-green-300 border border-green-500/30'
                      : 'bg-red-500/20 text-red-300 border border-red-500/30'}`}>
                    {result.success ? '✓ Done' : '✗ Failed'}
                  </div>
                ) : (
                  <button
                    id={`btn-action-${action.id}-${incidentId}`}
                    onClick={() => handleExecute(action)}
                    disabled={isExecuting}
                    className={`shrink-0 px-4 py-2 rounded-xl text-xs font-bold transition-all duration-200
                      ${isConfirming
                        ? 'bg-orange-500/20 text-orange-300 border border-orange-500/40 animate-pulse'
                        : isExecuting
                        ? 'bg-slate-700/50 text-slate-400 border border-slate-600/30 cursor-not-allowed'
                        : action.severity === 'danger'
                        ? 'bg-red-500/20 text-red-300 border border-red-500/40 hover:bg-red-500/30'
                        : 'bg-blue-500/20 text-blue-300 border border-blue-500/40 hover:bg-blue-500/30'
                      }`}
                  >
                    {isExecuting ? (
                      <span className="flex items-center gap-2">
                        <span className="w-3 h-3 border-2 border-slate-400 border-t-white rounded-full animate-spin" />
                        Running...
                      </span>
                    ) : isConfirming ? (
                      '⚠️ Confirm?'
                    ) : (
                      'Execute'
                    )}
                  </button>
                )}
              </div>

              {/* Result output */}
              {isDone && result.output && (
                <div className="mt-3 code-block text-green-300">
                  {result.simulated && (
                    <span className="text-yellow-400">[SIMULATED] </span>
                  )}
                  {result.output}
                  {result.error && <span className="text-red-400">{result.error}</span>}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default ActionButton;
