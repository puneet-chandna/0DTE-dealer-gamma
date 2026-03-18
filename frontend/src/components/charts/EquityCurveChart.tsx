/**
 * EquityCurveChart — Backtest equity curve with drawdown highlighting.
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

interface EquityCurveChartProps {
  equityCurve: number[];
  initialCash: number;
  height?: number;
  isLoading?: boolean;
}

function EquityCurveChartComponent({
  equityCurve,
  initialCash,
  height = 300,
  isLoading = false,
}: EquityCurveChartProps) {
  const chartData = useMemo(() => {
    if (!equityCurve || equityCurve.length === 0) return [];

    // Running max for drawdown detection
    let runningMax = equityCurve[0];

    return equityCurve.map((value, index) => {
      runningMax = Math.max(runningMax, value);
      const drawdown = ((value - runningMax) / runningMax) * 100;

      return {
        index,
        equity: value,
        drawdown,
        isDrawdown: drawdown < -1, // >1% drawdown
      };
    });
  }, [equityCurve]);

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
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-zinc-600 border-t-violet-400" />
      </div>
    );
  }

  if (chartData.length === 0) {
    return (
      <div
        className="flex items-center justify-center rounded-lg border border-zinc-800 bg-zinc-900/50"
        style={{ height }}
      >
        <p className="text-sm text-zinc-500">No equity data available</p>
      </div>
    );
  }

  const isPositive = totalReturn >= 0;
  const gradientColor = isPositive ? '#10b981' : '#ef4444';

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={chartData} margin={{ top: 10, right: 20, bottom: 10, left: 10 }}>
        <defs>
          <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={gradientColor} stopOpacity={0.3} />
            <stop offset="95%" stopColor={gradientColor} stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
        <XAxis
          dataKey="index"
          tick={{ fill: '#71717a', fontSize: 10 }}
          tickFormatter={(v) => `${v}`}
          interval="preserveStartEnd"
        />
        <YAxis
          domain={['auto', 'auto']}
          tick={{ fill: '#71717a', fontSize: 11 }}
          tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: '#18181b',
            border: '1px solid #3f3f46',
            borderRadius: '8px',
            fontSize: '12px',
          }}
          formatter={(value, name) => {
            if (name === 'equity' && typeof value === 'number') {
              return [`$${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`, 'Equity'];
            }
            return [value ?? 0, name ?? ''];
          }}
          labelFormatter={(label) => `Period ${label}`}
        />
        <ReferenceLine
          y={initialCash}
          stroke="#52525b"
          strokeDasharray="5 5"
          label={{ value: 'Initial', fill: '#52525b', fontSize: 10, position: 'right' }}
        />
        <Area
          type="monotone"
          dataKey="equity"
          stroke={gradientColor}
          strokeWidth={2}
          fill="url(#equityGradient)"
          dot={false}
          activeDot={{ r: 4, fill: gradientColor }}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export const EquityCurveChart = memo(EquityCurveChartComponent);
