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
      [...data].sort((a, b) => a.strike - b.strike).map((d) => ({
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
        <p className="text-sm text-[var(--text-secondary)]">Loading chart…</p>
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div
        className="flex items-center justify-center rounded-lg border border-zinc-800 bg-zinc-900/50"
        style={{ height }}
      >
        <p className="text-sm text-[var(--text-secondary)]">No skew data available</p>
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={chartData} margin={{ top: 10, right: 20, bottom: 20, left: 10 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--stroke)" />
        <XAxis
          dataKey="strike"
          type="number"
          domain={['dataMin', 'dataMax']}
          tick={{ fill: 'var(--text-secondary)', fontSize: 12 }}
          label={{ value: 'Strike', position: 'bottom', fill: 'var(--text-secondary)', fontSize: 12 }}
        />
        <YAxis
          width={80}
          tick={{ fill: 'var(--text-secondary)', fontSize: 12 }}
          label={{ value: 'Put − call IV (pp)', angle: -90, position: 'insideLeft', fill: 'var(--text-secondary)', fontSize: 12 }}
        />
        <Tooltip
          isAnimationActive={false}
          contentStyle={{
            backgroundColor: 'var(--surface-raised)',
            border: '1px solid var(--stroke)',
            borderRadius: '8px',
            fontSize: '14px',
            color: 'var(--text-primary)',
          }}
          formatter={(value, name) => {
            const v = typeof value === 'number' ? value : 0;
            const labels: Record<string, string> = {
              skew: 'Skew',
              callIV: 'Call IV',
              putIV: 'Put IV',
            };
            return [`${v.toFixed(2)}${name === 'skew' ? ' pp' : '%'}`, (labels[name ?? ''] || (name ?? ''))];
          }}
        />
        <ReferenceLine y={0} stroke="var(--text-muted)" strokeDasharray="5 5" />
        <Area
          isAnimationActive={false}
          type="linear"
          dataKey="skew"
          fill="var(--accent)"
          fillOpacity={0.1}
          stroke="none"
        />
        <Line
          isAnimationActive={false}
          type="linear"
          dataKey="skew"
          stroke="var(--accent)"
          strokeWidth={2}
          dot={{ fill: 'var(--accent)', r: 3 }}
          activeDot={{ r: 5, fill: 'var(--accent)' }}
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export const IVSkewChart = memo(IVSkewChartComponent);
