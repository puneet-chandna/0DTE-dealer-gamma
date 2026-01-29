/**
 * TimeSeriesChart - Historical Net GEX over time
 *
 * RULE: Use React.memo() for chart components
 * RULE: Throttle updates - max 1 render per 200ms
 */

'use client';

import { memo, useMemo } from 'react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import { format, parseISO } from 'date-fns';

interface TimeSeriesDataPoint {
  timestamp: string;
  netGex: number;
  netGexBillions: number;
}

interface TimeSeriesChartProps {
  data: TimeSeriesDataPoint[];
  isLoading?: boolean;
  height?: number;
  showZeroLine?: boolean;
}

// Custom tooltip
const CustomTooltip = ({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ value: number; payload: TimeSeriesDataPoint }>;
  label?: string;
}) => {
  if (!active || !payload || payload.length === 0) return null;

  const data = payload[0].payload;
  const isNegative = data.netGex < 0;

  let formattedTime = label || '';
  try {
    if (label) {
      formattedTime = format(parseISO(label), 'h:mm a');
    }
  } catch {
    // Keep original label if parsing fails
  }

  return (
    <div className="rounded-lg border border-zinc-700 bg-zinc-900/95 px-3 py-2 shadow-xl">
      <p className="text-xs text-zinc-400">{formattedTime}</p>
      <p
        className={`text-sm font-semibold ${
          isNegative ? 'text-rose-400' : 'text-emerald-400'
        }`}
      >
        Net GEX: {data.netGexBillions >= 0 ? '+' : ''}
        {data.netGexBillions.toFixed(2)}B
      </p>
    </div>
  );
};

function TimeSeriesChartComponent({
  data,
  isLoading = false,
  height = 250,
  showZeroLine = true,
}: TimeSeriesChartProps) {
  // Process and sort data by timestamp
  const chartData = useMemo(() => {
    if (!data || data.length === 0) return [];
    return [...data].sort(
      (a, b) =>
        new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
    );
  }, [data]);

  // Calculate Y domain
  const yDomain = useMemo(() => {
    if (chartData.length === 0) return [-1, 1];

    const maxAbs = Math.max(
      ...chartData.map((d) => Math.abs(d.netGexBillions)),
      0.5
    );
    const padding = maxAbs * 0.15;
    return [-(maxAbs + padding), maxAbs + padding];
  }, [chartData]);

  // Determine gradient based on latest value
  const latestValue = chartData.length > 0 ? chartData[chartData.length - 1].netGex : 0;
  const gradientId = latestValue < 0 ? 'gradientRed' : 'gradientGreen';
  const strokeColor = latestValue < 0 ? '#f43f5e' : '#10b981';

  if (isLoading) {
    return (
      <div
        className="flex items-center justify-center animate-pulse rounded-lg bg-zinc-800/50"
        style={{ height }}
      >
        <p className="text-zinc-500">Loading chart...</p>
      </div>
    );
  }

  if (chartData.length === 0) {
    return (
      <div
        className="flex items-center justify-center rounded-lg border border-zinc-800 bg-zinc-900/50"
        style={{ height }}
      >
        <p className="text-zinc-500">No historical data available</p>
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart
        data={chartData}
        margin={{ top: 10, right: 30, left: 0, bottom: 0 }}
      >
        <defs>
          <linearGradient id="gradientGreen" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
            <stop offset="95%" stopColor="#10b981" stopOpacity={0.05} />
          </linearGradient>
          <linearGradient id="gradientRed" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#f43f5e" stopOpacity={0.3} />
            <stop offset="95%" stopColor="#f43f5e" stopOpacity={0.05} />
          </linearGradient>
        </defs>

        <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />

        <XAxis
          dataKey="timestamp"
          tick={{ fill: '#71717a', fontSize: 10 }}
          tickLine={{ stroke: '#3f3f46' }}
          axisLine={{ stroke: '#3f3f46' }}
          tickFormatter={(value: string) => {
            try {
              return format(parseISO(value), 'H:mm');
            } catch {
              return '';
            }
          }}
          interval="preserveStartEnd"
        />

        <YAxis
          domain={yDomain}
          tick={{ fill: '#71717a', fontSize: 10 }}
          tickLine={{ stroke: '#3f3f46' }}
          axisLine={{ stroke: '#3f3f46' }}
          tickFormatter={(value: number) => `${value.toFixed(1)}B`}
          width={50}
        />

        <Tooltip content={<CustomTooltip />} />

        {showZeroLine && (
          <ReferenceLine y={0} stroke="#52525b" strokeWidth={1} />
        )}

        <Area
          type="monotone"
          dataKey="netGexBillions"
          stroke={strokeColor}
          strokeWidth={2}
          fill={`url(#${gradientId})`}
          dot={false}
          activeDot={{
            r: 4,
            fill: strokeColor,
            stroke: '#18181b',
            strokeWidth: 2,
          }}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export const TimeSeriesChart = memo(TimeSeriesChartComponent);
