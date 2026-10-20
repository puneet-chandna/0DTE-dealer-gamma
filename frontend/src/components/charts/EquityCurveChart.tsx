/**
 * EquityCurveChart — Backtest equity curve with drawdown highlighting.
 */

'use client';

import { memo, useMemo } from 'react';
import { formatMarketTimestamp } from '@/lib/utils';
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

interface EquityCurveChartProps {
  equityCurve: number[];
  initialCash: number;
  timestamps?: string[];
  height?: number;
  isLoading?: boolean;
}

function EquityCurveChartComponent({
  equityCurve,
  initialCash,
  timestamps,
  height = 300,
  isLoading = false,
}: EquityCurveChartProps) {
  const hasTimestamps = timestamps?.length === equityCurve.length
    && timestamps.every((timestamp) => Number.isFinite(Date.parse(timestamp)));
  const chartData = useMemo(() => {
    if (!equityCurve || equityCurve.length === 0) return [];

    // Running max for drawdown detection
    let runningMax = initialCash;

    return equityCurve.map((value, index) => {
      runningMax = Math.max(runningMax, value);
      const drawdown = ((value - runningMax) / runningMax) * 100;

      return {
        index,
        time: hasTimestamps ? Date.parse(timestamps![index]) : index,
        equity: value,
        drawdown,
        isDrawdown: drawdown < -1, // >1% drawdown
      };
    });
  }, [equityCurve, timestamps, initialCash, hasTimestamps]);

  const totalReturn = useMemo(() => {
    if (equityCurve.length === 0) return 0;
    return ((equityCurve[equityCurve.length - 1] - initialCash) / initialCash) * 100;
  }, [equityCurve, initialCash]);

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

  if (chartData.length === 0) {
    return (
      <div
        className="flex items-center justify-center rounded-lg border border-zinc-800 bg-zinc-900/50"
        style={{ height }}
      >
        <p className="text-sm text-[var(--text-secondary)]">No equity data available</p>
      </div>
    );
  }

  const isPositive = totalReturn >= 0;
  const gradientColor = isPositive ? 'var(--positive)' : 'var(--negative)';

  return (
    <div className="space-y-2">
      <ResponsiveContainer width="100%" height={height}>
        <AreaChart data={chartData} margin={{ top: 10, right: 20, bottom: 10, left: 10 }}>
          <defs>
            <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={gradientColor} stopOpacity={0.3} />
              <stop offset="95%" stopColor={gradientColor} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--stroke)" />
          <XAxis
            dataKey="time"
            type="number"
            scale={hasTimestamps ? 'time' : 'linear'}
            domain={['dataMin', 'dataMax']}
            tick={{ fill: 'var(--text-secondary)', fontSize: 12 }}
            tickFormatter={(value: number | string) => hasTimestamps ? new Date(value).toLocaleString('en-US', { timeZone: 'America/New_York', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZoneName: 'short' }) : String(value)}
            interval="preserveStartEnd"
          />
          <YAxis
            domain={['auto', 'auto']}
            tick={{ fill: 'var(--text-secondary)', fontSize: 12 }}
            width={100}
            tickFormatter={(v: number) => `$${v.toLocaleString('en-US', { maximumFractionDigits: 2 })}`}
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
              if (name === 'equity' && typeof value === 'number') {
                return [`$${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`, 'Equity'];
              }
              return [value ?? 0, name ?? ''];
            }}
            labelFormatter={(label) => hasTimestamps ? (formatMarketTimestamp(new Date(Number(label)).toISOString()) ?? String(label)) : `Period ${label}`}
          />
          <ReferenceLine
            y={initialCash}
            stroke="var(--text-muted)"
            strokeDasharray="5 5"
            label={{ value: 'Initial', fill: 'var(--text-secondary)', fontSize: 12, position: 'insideTopRight' }}
          />
          <Area
            isAnimationActive={false}
            type="linear"
            dataKey="equity"
            stroke={gradientColor}
            strokeWidth={2}
            fill="url(#equityGradient)"
            dot={false}
            activeDot={{ r: 4, fill: gradientColor }}
          />
        </AreaChart>
      </ResponsiveContainer>
      <p className="text-sm text-[var(--text-muted)]">{hasTimestamps ? 'Capture time (ET), spaced by elapsed time.' : 'Observation index; complete timestamps are unavailable.'} Equity in dollars.</p>
    </div>
  );
}

export const EquityCurveChart = memo(EquityCurveChartComponent);
