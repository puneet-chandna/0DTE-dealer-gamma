/**
 * IVSkewChart — IV skew (put IV - call IV) across strikes.
 *
 * Positive skew = puts more expensive (normal for equities).
 */

'use client';

import { memo, useMemo } from 'react';
import {
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Area,
  ComposedChart,
} from 'recharts';
import type { IVSkewPoint } from '@/types';

interface IVSkewChartProps {
  data: IVSkewPoint[];
  height?: number;
  isLoading?: boolean;
}

function IVSkewChartComponent({
  data,
  height = 300,
  isLoading = false,
}: IVSkewChartProps) {
  const chartData = useMemo(
    () =>
      data.map((d) => ({
        strike: d.strike,
        skew: d.skew * 100,
        callIV: d.call_iv * 100,
        putIV: d.put_iv * 100,
        moneyness: d.moneyness,
      })),
    [data]
  );

  if (isLoading) {
    return (
      <div
        className="flex items-center justify-center rounded-lg border border-zinc-800 bg-zinc-900/50"
        style={{ height }}
      >
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-zinc-600 border-t-violet-400" />
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div
        className="flex items-center justify-center rounded-lg border border-zinc-800 bg-zinc-900/50"
        style={{ height }}
      >
        <p className="text-sm text-zinc-500">No skew data available</p>
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={chartData} margin={{ top: 10, right: 20, bottom: 20, left: 10 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
        <XAxis
          dataKey="strike"
          tick={{ fill: '#71717a', fontSize: 11 }}
          label={{ value: 'Strike', position: 'bottom', fill: '#52525b', fontSize: 11 }}
        />
        <YAxis
          tick={{ fill: '#71717a', fontSize: 11 }}
          label={{ value: 'Skew (%)', angle: -90, position: 'insideLeft', fill: '#52525b', fontSize: 11 }}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: '#18181b',
            border: '1px solid #3f3f46',
            borderRadius: '8px',
            fontSize: '12px',
          }}
          formatter={(value, name) => {
            const v = typeof value === 'number' ? value : 0;
            const labels: Record<string, string> = {
              skew: 'Skew',
              callIV: 'Call IV',
              putIV: 'Put IV',
            };
            return [`${v.toFixed(2)}%`, (labels[name ?? ''] || (name ?? ''))];
          }}
        />
        <ReferenceLine y={0} stroke="#52525b" strokeDasharray="5 5" />
        <Area
          type="monotone"
          dataKey="skew"
          fill="#8b5cf6"
          fillOpacity={0.1}
          stroke="none"
        />
        <Line
          type="monotone"
          dataKey="skew"
          stroke="#8b5cf6"
          strokeWidth={2}
          dot={{ fill: '#8b5cf6', r: 3 }}
          activeDot={{ r: 5, fill: '#a78bfa' }}
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export const IVSkewChart = memo(IVSkewChartComponent);
