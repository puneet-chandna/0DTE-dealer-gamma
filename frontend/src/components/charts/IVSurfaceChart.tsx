/**
 * IVSurfaceChart — IV smile scatter plot (calls vs puts).
 *
 * X-axis: relative moneyness ((strike-spot)/spot), Y-axis: implied volatility.
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

  const minMoneyness = Math.min(0, ...data.map((point) => point.moneyness));
  const maxMoneyness = Math.max(0, ...data.map((point) => point.moneyness));
  const rawTickStep = Math.max(Math.abs(minMoneyness), maxMoneyness, Number.EPSILON) / 4;
  const tickMagnitude = 10 ** Math.floor(Math.log10(rawTickStep));
  const tickUnit = rawTickStep / tickMagnitude;
  const tickStep = (tickUnit <= 1 ? 1 : tickUnit <= 2 ? 2 : tickUnit <= 5 ? 5 : 10) * tickMagnitude;
  const firstTick = Math.ceil(minMoneyness / tickStep);
  const lastTick = Math.floor(maxMoneyness / tickStep);
  const xTicks = Array.from({ length: lastTick - firstTick + 1 }, (_, index) => (firstTick + index) * tickStep);

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
        <p className="text-sm text-[var(--text-secondary)]">No IV data available</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex gap-5 text-sm text-[var(--text-secondary)]">
        <span className="inline-flex items-center gap-2"><svg aria-hidden="true" width="12" height="12"><circle cx="6" cy="6" r="4" fill="var(--negative)" /></svg>Calls</span>
        <span className="inline-flex items-center gap-2"><svg aria-hidden="true" width="12" height="12"><path d="M6 0 12 6 6 12 0 6Z" fill="var(--positive)" /></svg>Puts</span>
      </div>
      <ResponsiveContainer width="100%" height={height}>
        <ScatterChart margin={{ top: 10, right: 20, bottom: 20, left: 10 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--stroke)" />
          <XAxis
            dataKey="moneyness"
            type="number"
            name="Relative moneyness"
            ticks={xTicks}
            domain={[(min: number) => Math.min(0, min), (max: number) => Math.max(0, max)]}
            tickFormatter={(value: number) => `${(value * 100).toFixed(0)}%`}
            tick={{ fill: 'var(--text-secondary)', fontSize: 12 }}
            label={{ value: 'Relative moneyness (K−S)/S', position: 'bottom', fill: 'var(--text-secondary)', fontSize: 12 }}
          />
          <YAxis
            dataKey="iv"
            width={80}
            tickFormatter={(value: number) => `${value.toFixed(0)}%`}
            type="number"
            name="IV"
            tick={{ fill: 'var(--text-secondary)', fontSize: 12 }}
            label={{ value: 'IV (%)', angle: -90, position: 'insideLeft', fill: 'var(--text-secondary)', fontSize: 12 }}
          />
          <Tooltip
            isAnimationActive={false}
            cursor={{ strokeDasharray: '3 3', stroke: 'var(--text-muted)' }}
            contentStyle={{
              backgroundColor: 'var(--surface-raised)',
              border: '1px solid var(--stroke)',
              borderRadius: '8px',
              fontSize: '14px',
              color: 'var(--text-primary)',
            }}
            formatter={(value, name) => {
              const v = typeof value === 'number' ? value : 0;
              if (name === 'IV') return [`${v.toFixed(2)}%`, 'IV'];
              if (name === 'Relative moneyness') return [`${(v * 100).toFixed(2)}%`, '(K−S)/S'];
              return [v, name ?? ''];
            }}
          />
          <ReferenceLine
            x={0}
            stroke="var(--accent)"
            strokeDasharray="5 5"
            strokeWidth={1}
            label={{ value: 'ATM', fill: 'var(--accent)', fontSize: 12, position: 'insideTopLeft' }}
          />
          <Scatter
            isAnimationActive={false}
            name="Calls"
            data={callData}
            fill="var(--negative)"
            fillOpacity={0.7}
            shape="circle"
            r={4}
          />
          <Scatter
            isAnimationActive={false}
            name="Puts"
            data={putData}
            fill="var(--positive)"
            fillOpacity={0.7}
            shape="diamond"
            r={4}
          />
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}

export const IVSurfaceChart = memo(IVSurfaceChartComponent);
