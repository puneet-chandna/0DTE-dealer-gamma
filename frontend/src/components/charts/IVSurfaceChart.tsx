/**
 * IVSurfaceChart — IV smile scatter plot (calls vs puts).
 *
 * X-axis: moneyness (strike/spot), Y-axis: implied volatility.
 * Calls in rose, puts in emerald.
 */

'use client';

import { memo, useMemo } from 'react';
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import type { IVSurfacePoint } from '@/types';

interface IVSurfaceChartProps {
  data: IVSurfacePoint[];
  spotPrice?: number;
  height?: number;
  isLoading?: boolean;
}

function IVSurfaceChartComponent({
  data,
  height = 300,
  isLoading = false,
}: IVSurfaceChartProps) {
  const callData = useMemo(
    () => data.filter((d) => d.type === 'call').map((d) => ({
      moneyness: d.moneyness,
      iv: d.iv * 100,
      strike: d.strike,
      midPrice: d.mid_price,
    })),
    [data]
  );

  const putData = useMemo(
    () => data.filter((d) => d.type === 'put').map((d) => ({
      moneyness: d.moneyness,
      iv: d.iv * 100,
      strike: d.strike,
      midPrice: d.mid_price,
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
        <p className="text-sm text-zinc-500">No IV data available</p>
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <ScatterChart margin={{ top: 10, right: 20, bottom: 20, left: 10 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
        <XAxis
          dataKey="moneyness"
          type="number"
          name="Moneyness"
          domain={['auto', 'auto']}
          tick={{ fill: '#71717a', fontSize: 11 }}
          label={{ value: 'Moneyness (K/S)', position: 'bottom', fill: '#52525b', fontSize: 11 }}
        />
        <YAxis
          dataKey="iv"
          type="number"
          name="IV"
          tick={{ fill: '#71717a', fontSize: 11 }}
          label={{ value: 'IV (%)', angle: -90, position: 'insideLeft', fill: '#52525b', fontSize: 11 }}
        />
        <Tooltip
          cursor={{ strokeDasharray: '3 3', stroke: '#52525b' }}
          contentStyle={{
            backgroundColor: '#18181b',
            border: '1px solid #3f3f46',
            borderRadius: '8px',
            fontSize: '12px',
          }}
          formatter={(value, name) => {
            const v = typeof value === 'number' ? value : 0;
            if (name === 'iv') return [`${v.toFixed(2)}%`, 'IV'];
            if (name === 'moneyness') return [v.toFixed(4), 'Moneyness'];
            return [v, name ?? ''];
          }}
        />
        <ReferenceLine
          x={1.0}
          stroke="#8b5cf6"
          strokeDasharray="5 5"
          strokeWidth={1}
          label={{ value: 'ATM', fill: '#8b5cf6', fontSize: 10, position: 'top' }}
        />
        <Scatter
          name="Calls"
          data={callData}
          fill="#f43f5e"
          fillOpacity={0.7}
          shape="circle"
          r={4}
        />
        <Scatter
          name="Puts"
          data={putData}
          fill="#10b981"
          fillOpacity={0.7}
          shape="diamond"
          r={4}
        />
      </ScatterChart>
    </ResponsiveContainer>
  );
}

export const IVSurfaceChart = memo(IVSurfaceChartComponent);
