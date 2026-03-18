/**
 * TechnicalOverlayChart — Price with Bollinger Bands, ATR, and RSI sub-panel.
 *
 * Uses Recharts ComposedChart for multi-layer overlays.
 */

'use client';

import { memo, useMemo } from 'react';
import {
  ComposedChart,
  Line,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import type { TechnicalIndicatorPoint } from '@/types';

interface TechnicalOverlayChartProps {
  data: TechnicalIndicatorPoint[];
  indicators: string[];
  height?: number;
  isLoading?: boolean;
}

function formatDate(timestamp: string): string {
  try {
    const d = new Date(timestamp);
    return `${d.getMonth() + 1}/${d.getDate()}`;
  } catch {
    return timestamp.slice(0, 10);
  }
}

function TechnicalOverlayChartComponent({
  data,
  indicators,
  height = 350,
  isLoading = false,
}: TechnicalOverlayChartProps) {
  const chartData = useMemo(
    () =>
      data.map((d) => ({
        date: formatDate(d.timestamp),
        close: d.close,
        atr: d.atr,
        rsi: d.rsi,
        bbUpper: d.bb_upper,
        bbMid: d.bb_mid,
        bbLower: d.bb_lower,
        // For the band area fill
        bbRange: d.bb_upper !== null && d.bb_lower !== null
          ? [d.bb_lower, d.bb_upper]
          : undefined,
      })),
    [data]
  );

  const hasBBands = indicators.includes('BBANDS');
  const hasATR = indicators.includes('ATR');
  const hasRSI = indicators.includes('RSI');

  if (isLoading) {
    return (
      <div
        className="flex items-center justify-center rounded-lg border border-zinc-800 bg-zinc-900/50"
        style={{ height: height + (hasRSI ? 150 : 0) }}
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
        <p className="text-sm text-zinc-500">No price data available</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {/* Main price chart with Bollinger Bands */}
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={chartData} margin={{ top: 10, right: 20, bottom: 5, left: 10 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
          <XAxis
            dataKey="date"
            tick={{ fill: '#71717a', fontSize: 10 }}
            interval="preserveStartEnd"
          />
          <YAxis
            yAxisId="price"
            domain={['auto', 'auto']}
            tick={{ fill: '#71717a', fontSize: 11 }}
            label={{ value: 'Price', angle: -90, position: 'insideLeft', fill: '#52525b', fontSize: 11 }}
          />
          {hasATR && (
            <YAxis
              yAxisId="atr"
              orientation="right"
              domain={['auto', 'auto']}
              tick={{ fill: '#f59e0b', fontSize: 10 }}
              label={{ value: 'ATR', angle: 90, position: 'insideRight', fill: '#f59e0b', fontSize: 10 }}
            />
          )}
          <Tooltip
            contentStyle={{
              backgroundColor: '#18181b',
              border: '1px solid #3f3f46',
              borderRadius: '8px',
              fontSize: '12px',
            }}
            formatter={(value, name) => {
              if (value == null) return ['—', name ?? ''];
              const labels: Record<string, string> = {
                close: 'Close',
                bbUpper: 'BB Upper',
                bbMid: 'BB Mid',
                bbLower: 'BB Lower',
                atr: 'ATR',
              };
              return [
                typeof value === 'number' ? value.toFixed(2) : value,
                (labels[name ?? ''] || (name ?? '')),
              ];
            }}
          />

          {/* Bollinger Bands area */}
          {hasBBands && (
            <>
              <Area
                yAxisId="price"
                type="monotone"
                dataKey="bbUpper"
                stroke="none"
                fill="#3b82f6"
                fillOpacity={0.05}
                connectNulls={false}
              />
              <Area
                yAxisId="price"
                type="monotone"
                dataKey="bbLower"
                stroke="none"
                fill="#09090b"
                fillOpacity={1}
                connectNulls={false}
              />
              <Line
                yAxisId="price"
                type="monotone"
                dataKey="bbUpper"
                stroke="#3b82f6"
                strokeWidth={1}
                strokeDasharray="4 2"
                dot={false}
                connectNulls={false}
              />
              <Line
                yAxisId="price"
                type="monotone"
                dataKey="bbMid"
                stroke="#3b82f6"
                strokeWidth={1}
                strokeOpacity={0.5}
                dot={false}
                connectNulls={false}
              />
              <Line
                yAxisId="price"
                type="monotone"
                dataKey="bbLower"
                stroke="#3b82f6"
                strokeWidth={1}
                strokeDasharray="4 2"
                dot={false}
                connectNulls={false}
              />
            </>
          )}

          {/* Price line */}
          <Line
            yAxisId="price"
            type="monotone"
            dataKey="close"
            stroke="#e4e4e7"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, fill: '#e4e4e7' }}
          />

          {/* ATR */}
          {hasATR && (
            <Line
              yAxisId="atr"
              type="monotone"
              dataKey="atr"
              stroke="#f59e0b"
              strokeWidth={1.5}
              dot={false}
              connectNulls={false}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>

      {/* RSI sub-panel */}
      {hasRSI && (
        <ResponsiveContainer width="100%" height={140}>
          <ComposedChart data={chartData} margin={{ top: 5, right: 20, bottom: 15, left: 10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
            <XAxis
              dataKey="date"
              tick={{ fill: '#71717a', fontSize: 10 }}
              interval="preserveStartEnd"
            />
            <YAxis
              domain={[0, 100]}
              ticks={[20, 30, 50, 70, 80]}
              tick={{ fill: '#71717a', fontSize: 10 }}
              label={{ value: 'RSI', angle: -90, position: 'insideLeft', fill: '#52525b', fontSize: 10 }}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#18181b',
                border: '1px solid #3f3f46',
                borderRadius: '8px',
                fontSize: '12px',
              }}
              formatter={(value) => [
                typeof value === 'number' ? value.toFixed(1) : '—',
                'RSI',
              ]}
            />
            {/* Overbought/Oversold zones */}
            <ReferenceLine y={70} stroke="#ef4444" strokeDasharray="4 4" strokeOpacity={0.5} />
            <ReferenceLine y={30} stroke="#22c55e" strokeDasharray="4 4" strokeOpacity={0.5} />
            <ReferenceLine y={50} stroke="#52525b" strokeDasharray="2 4" />

            <Area
              type="monotone"
              dataKey="rsi"
              fill="#8b5cf6"
              fillOpacity={0.1}
              stroke="none"
              connectNulls={false}
            />
            <Line
              type="monotone"
              dataKey="rsi"
              stroke="#8b5cf6"
              strokeWidth={1.5}
              dot={false}
              activeDot={{ r: 3, fill: '#a78bfa' }}
              connectNulls={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

export const TechnicalOverlayChart = memo(TechnicalOverlayChartComponent);
