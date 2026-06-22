import React, {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { MetricDataPoint } from '../types';

interface TimelineChartProps {
  metrics: MetricDataPoint[];
  incidentTimestamp?: number;
  title?: string;
  metricName?: string;
}

const COLORS = {
  latency: '#3b82f6',
  error_rate: '#ef4444',
  cpu_usage: '#f59e0b',
  memory_usage: '#8b5cf6',
  default: '#06b6d4',
};

const TimelineChart: React.FC<TimelineChartProps> = ({
  metrics,
  incidentTimestamp,
  title = 'Metric Timeline',
  metricName,
}) => {
  // Group by timestamp and normalize
  const chartData = metrics
    .filter(m => !metricName || m.metric_name === metricName)
    .sort((a, b) => a.timestamp - b.timestamp)
    .slice(-100)
    .map(m => ({
      time: new Date(m.timestamp * 1000).toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
      }),
      value: parseFloat(m.value.toFixed(2)),
      timestamp: m.timestamp,
      service: m.service,
    }));

  // If no real data, generate demo data
  const displayData = chartData.length > 0 ? chartData : generateDemoData(incidentTimestamp);

  const color = COLORS[metricName as keyof typeof COLORS] || COLORS.default;

  const CustomTooltip = ({ active, payload, label }: {
    active?: boolean;
    payload?: Array<{ value: number; name: string }>;
    label?: string;
  }) => {
    if (active && payload && payload.length) {
      return (
        <div className="glass-card p-3 text-xs">
          <p className="text-slate-400 mb-1">{label}</p>
          {payload.map((p, i) => (
            <p key={i} style={{ color }} className="font-semibold">
              {p.name}: {p.value}
            </p>
          ))}
        </div>
      );
    }
    return null;
  };

  return (
    <div className="glass-card p-4">
      <h3 className="text-sm font-semibold text-white mb-3">{title}</h3>
      <ResponsiveContainer width="100%" height={180}>
        <AreaChart data={displayData} margin={{ top: 5, right: 10, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id={`grad-${metricName}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={color} stopOpacity={0.3} />
              <stop offset="95%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
          <XAxis
            dataKey="time"
            tick={{ fontSize: 10, fill: '#64748b' }}
            tickLine={false}
            axisLine={{ stroke: 'rgba(255,255,255,0.05)' }}
          />
          <YAxis
            tick={{ fontSize: 10, fill: '#64748b' }}
            tickLine={false}
            axisLine={false}
            width={40}
          />
          <Tooltip content={<CustomTooltip />} />
          {incidentTimestamp && (
            <ReferenceLine
              x={new Date(incidentTimestamp * 1000).toLocaleTimeString('en-US', {
                hour: '2-digit',
                minute: '2-digit',
                hour12: false,
              })}
              stroke="#ef4444"
              strokeDasharray="4 4"
              label={{ value: '🚨 Anomaly', fill: '#ef4444', fontSize: 10 }}
            />
          )}
          <Area
            type="monotone"
            dataKey="value"
            name={metricName || 'value'}
            stroke={color}
            strokeWidth={2}
            fill={`url(#grad-${metricName})`}
            dot={false}
            activeDot={{ r: 4, fill: color, stroke: 'white', strokeWidth: 2 }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
};

function generateDemoData(incidentTs?: number): Array<{ time: string; value: number; timestamp: number }> {
  const now = incidentTs || Date.now() / 1000;
  const points = 40;
  return Array.from({ length: points }, (_, i) => {
    const ts = now - (points - i) * 60;
    const isAnomalyWindow = i >= 32;
    const baseVal = 150;
    const noise = Math.random() * 30 - 15;
    const spike = isAnomalyWindow ? (i - 32) * 800 : 0;
    return {
      time: new Date(ts * 1000).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false }),
      value: Math.max(0, baseVal + noise + spike),
      timestamp: ts,
    };
  });
}

export default TimelineChart;
