/**
 * GEXBarChart - Strike-by-strike GEX visualization
 *
 * Primary visualization for the dashboard.
 * RULE: Use React.memo() for chart components (master_plan.md)
 * RULE: Throttle updates - max 1 render per 200ms
 *
 * Visual:
 * - Red bars: Negative GEX (Calls) 
 * - Green bars: Positive GEX (Puts)
 * - Vertical dashed line: Current spot price
 * - Horizontal reference line: Zero Gamma Level
 */

'use client';

import { memo, useMemo, useRef, useEffect, useState } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
  Cell,
} from 'recharts';

interface GEXBarChartData {
  strike: number;
  gex: number;
  gexBillions: number;
}

interface GEXBarChartProps {
  data: GEXBarChartData[];
  spotPrice: number;
  zeroGammaLevel?: number | null;
  isLoading?: boolean;
  height?: number;
}

// Throttle hook to limit re-renders
function useThrottledValue<T>(value: T, limit: number): T {
  const [throttledValue, setThrottledValue] = useState(value);
  const lastRanRef = useRef(0);

  useEffect(() => {
    const handler = setTimeout(() => {
      if (Date.now() - lastRanRef.current >= limit) {
        setThrottledValue(value);
        lastRanRef.current = Date.now();
      }
    }, limit - (Date.now() - lastRanRef.current));

    return () => clearTimeout(handler);
  }, [value, limit]);

  return throttledValue;
}

// Custom tooltip component
const CustomTooltip = ({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ value: number; payload: GEXBarChartData }>;
  label?: number;
}) => {
  if (!active || !payload || payload.length === 0) return null;

  const data = payload[0].payload;
  const isNegative = data.gex < 0;

  return (
    <div className="rounded-lg border border-zinc-700 bg-zinc-900/95 px-3 py-2 shadow-xl">
      <p className="text-xs text-zinc-400">Strike: ${label?.toLocaleString()}</p>
      <p
        className={`text-sm font-semibold ${
          isNegative ? 'text-rose-400' : 'text-emerald-400'
        }`}
      >
        GEX: {data.gexBillions >= 0 ? '+' : ''}
        {data.gexBillions.toFixed(3)}B
      </p>
    </div>
  );
};

function GEXBarChartComponent({
  data,
  spotPrice,
  zeroGammaLevel,
  isLoading = false,
  height = 350,
}: GEXBarChartProps) {
  // Throttle data updates to max 5 per second (200ms)
  const throttledData = useThrottledValue(data, 200);

  // Memoize chart data processing
  const chartData = useMemo(() => {
    if (!throttledData || throttledData.length === 0) return [];
    
    // Sort by strike price
    return [...throttledData].sort((a, b) => a.strike - b.strike);
  }, [throttledData]);

  // Calculate Y axis domain for balanced view
  const yDomain = useMemo(() => {
    if (chartData.length === 0) return [-1, 1];
    
    const maxAbs = Math.max(
      ...chartData.map((d) => Math.abs(d.gexBillions)),
      0.1 // Minimum scale
    );
    const padding = maxAbs * 0.1;
    return [-(maxAbs + padding), maxAbs + padding];
  }, [chartData]);

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
        <p className="text-zinc-500">No data available</p>
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart
        data={chartData}
        margin={{ top: 20, right: 30, left: 20, bottom: 5 }}
      >
        <CartesianGrid
          strokeDasharray="3 3"
          stroke="#27272a"
          vertical={false}
        />
        <XAxis
          dataKey="strike"
          tick={{ fill: '#71717a', fontSize: 11 }}
          tickLine={{ stroke: '#3f3f46' }}
          axisLine={{ stroke: '#3f3f46' }}
          tickFormatter={(value: number) => {
            // Show fewer labels for readability
            return value % 25 === 0 ? value.toString() : '';
          }}
        />
        <YAxis
          domain={yDomain}
          tick={{ fill: '#71717a', fontSize: 11 }}
          tickLine={{ stroke: '#3f3f46' }}
          axisLine={{ stroke: '#3f3f46' }}
          tickFormatter={(value: number) => `${value.toFixed(1)}B`}
          width={60}
        />
        <Tooltip content={<CustomTooltip />} />

        {/* Zero line */}
        <ReferenceLine y={0} stroke="#52525b" strokeWidth={1} />

        {/* Spot price vertical line */}
        <ReferenceLine
          x={spotPrice}
          stroke="#fbbf24"
          strokeWidth={2}
          strokeDasharray="5 5"
          label={{
            value: `Spot: $${spotPrice.toLocaleString()}`,
            position: 'top',
            fill: '#fbbf24',
            fontSize: 11,
          }}
        />

        {/* Zero Gamma Level horizontal reference */}
        {zeroGammaLevel && (
          <ReferenceLine
            x={zeroGammaLevel}
            stroke="#a78bfa"
            strokeWidth={2}
            strokeDasharray="8 4"
            label={{
              value: `0Γ: $${zeroGammaLevel.toLocaleString()}`,
              position: 'top',
              fill: '#a78bfa',
              fontSize: 11,
              offset: 15,
            }}
          />
        )}

        {/* GEX bars with conditional coloring */}
        <Bar dataKey="gexBillions" radius={[2, 2, 0, 0]}>
          {chartData.map((entry, index) => (
            <Cell
              key={`cell-${index}`}
              fill={entry.gex < 0 ? '#f43f5e' : '#10b981'}
              fillOpacity={0.8}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

// Export memoized component for performance
export const GEXBarChart = memo(GEXBarChartComponent);
