/**
 * TechnicalOverlayChart — Price with Bollinger Bands, ATR, and RSI sub-panel.
 *
 * Uses Recharts ComposedChart for multi-layer overlays.
 */

'use client';

import { formatMarketTimestamp } from '@/lib/utils';
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

function TechnicalOverlayChartComponent({
  data,
  indicators,
  height = 350,
  isLoading = false,
}: TechnicalOverlayChartProps) {
  const chartData = useMemo(
    () =>
      [...data]
        .map((d) => ({ d, time: Date.parse(d.timestamp) }))
        .filter((entry) => Number.isFinite(entry.time))
        .sort((a, b) => a.time - b.time)
        .map(({ d, time }) => ({
          time,
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
  const hasAnyIndicatorValues = useMemo(() => {
    return data.some((point) => {
      if (hasATR && point.atr !== null) return true;
      if (hasRSI && point.rsi !== null) return true;
      if (hasBBands && (point.bb_upper !== null || point.bb_mid !== null || point.bb_lower !== null)) {
        return true;
      }
      return false;
    });
  }, [data, hasATR, hasBBands, hasRSI]);
  const needsMoreHistory =
    data.length > 0 &&
    (hasATR || hasRSI || hasBBands) &&
    !hasAnyIndicatorValues;
  const legendItems = [
    { label: 'Close', color: 'var(--text-primary)' },
    ...(hasBBands ? [{ label: 'Bollinger Bands', color: 'var(--accent)' }] : []),
    ...(hasATR ? [{ label: 'ATR', color: 'var(--warning)' }] : []),
    ...(hasRSI ? [{ label: 'RSI', color: 'var(--accent)' }] : []),
  ];

  if (isLoading) {
    return (
      <div
        className="flex items-center justify-center rounded-lg border border-zinc-800 bg-zinc-900/50"
        style={{ height: height + (hasRSI ? 150 : 0) }}
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
        <p className="text-sm text-[var(--text-secondary)]">No price data available</p>
      </div>
    );
  }

  if (needsMoreHistory) {
    return (
      <div
        className="flex flex-col items-center justify-center rounded-lg border border-zinc-800 bg-zinc-900/50 px-6 text-center"
        style={{ height }}
      >
        <p className="text-sm text-[var(--text-primary)]">
          More observations are needed before ATR, RSI, and Bollinger Bands can be plotted.
        </p>
        <p className="mt-2 max-w-xl text-sm text-[var(--text-secondary)]">
          The available price history does not contain enough bars at this interval.
          Choose a longer period or a shorter interval.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <p className="text-sm text-[var(--text-muted)]">Observation time (ET), spaced by elapsed time.</p>
      <div className="flex flex-wrap gap-2 text-sm text-[var(--text-secondary)]">
        {legendItems.map((item) => (
          <div
            key={item.label}
            className="inline-flex items-center gap-2 rounded-full border border-zinc-800 bg-zinc-900/60 px-2.5 py-1"
          >
            <span
              className="h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: item.color }}
            />
            <span>{item.label}</span>
          </div>
        ))}
      </div>

      {/* Main price chart with Bollinger Bands */}
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={chartData} margin={{ top: 10, right: 20, bottom: 5, left: 10 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--stroke)" />
          <XAxis
            dataKey="time"
            type="number"
            scale="time"
            domain={['dataMin', 'dataMax']}
            tickFormatter={(value: number) => new Date(value).toLocaleString('en-US', { timeZone: 'America/New_York', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
            tick={{ fill: 'var(--text-secondary)', fontSize: 12 }}
            interval="preserveStartEnd"
          />
          <YAxis
            yAxisId="price"
            width={80}
            domain={['auto', 'auto']}
            tick={{ fill: 'var(--text-secondary)', fontSize: 12 }}
            label={{ value: 'Price ($)', angle: -90, position: 'insideLeft', fill: 'var(--text-secondary)', fontSize: 12 }}
          />
          {hasATR && (
            <YAxis
              yAxisId="atr"
              orientation="right"
              width={80}
              domain={['auto', 'auto']}
              tick={{ fill: 'var(--warning)', fontSize: 12 }}
              label={{ value: 'ATR', angle: 90, position: 'insideRight', fill: 'var(--warning)', fontSize: 12 }}
            />
          )}
          <Tooltip
            isAnimationActive={false}
            labelFormatter={(value) => formatMarketTimestamp(new Date(Number(value)).toISOString()) ?? ''}
            contentStyle={{
              backgroundColor: 'var(--surface-raised)',
              border: '1px solid var(--stroke)',
              borderRadius: '8px',
              fontSize: '14px',
              color: 'var(--text-primary)',
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
                isAnimationActive={false}
                yAxisId="price"
                type="linear"
                dataKey="bbRange"
                stroke="none"
                fill="var(--accent)"
                fillOpacity={0.08}
                connectNulls={false}
              />
              <Line
                isAnimationActive={false}
                yAxisId="price"
                type="linear"
                dataKey="bbUpper"
                stroke="var(--accent)"
                strokeWidth={1}
                strokeDasharray="4 2"
                dot={false}
                connectNulls={false}
              />
              <Line
                isAnimationActive={false}
                yAxisId="price"
                type="linear"
                dataKey="bbMid"
                stroke="var(--accent)"
                strokeWidth={1}
                strokeOpacity={0.5}
                dot={false}
                connectNulls={false}
              />
              <Line
                isAnimationActive={false}
                yAxisId="price"
                type="linear"
                dataKey="bbLower"
                stroke="var(--accent)"
                strokeWidth={1}
                strokeDasharray="4 2"
                dot={false}
                connectNulls={false}
              />
            </>
          )}

          {/* Price line */}
          <Line
            isAnimationActive={false}
            yAxisId="price"
            type="linear"
            dataKey="close"
            stroke="var(--text-primary)"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, fill: 'var(--text-primary)' }}
          />

          {/* ATR */}
          {hasATR && (
            <Line
              isAnimationActive={false}
              yAxisId="atr"
              type="linear"
              dataKey="atr"
              stroke="var(--warning)"
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
            <CartesianGrid strokeDasharray="3 3" stroke="var(--stroke)" />
            <XAxis
              dataKey="time"
              type="number"
              scale="time"
              domain={['dataMin', 'dataMax']}
              tickFormatter={(value: number) => new Date(value).toLocaleString('en-US', { timeZone: 'America/New_York', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
              tick={{ fill: 'var(--text-secondary)', fontSize: 12 }}
              interval="preserveStartEnd"
            />
            <YAxis
              domain={[0, 100]}
              ticks={[20, 30, 50, 70, 80]}
              tick={{ fill: 'var(--text-secondary)', fontSize: 12 }}
              label={{ value: 'RSI', angle: -90, position: 'insideLeft', fill: 'var(--text-secondary)', fontSize: 12 }}
            />
            <Tooltip
              isAnimationActive={false}
              labelFormatter={(value) => formatMarketTimestamp(new Date(Number(value)).toISOString()) ?? ''}
              contentStyle={{
                backgroundColor: 'var(--surface-raised)',
                border: '1px solid var(--stroke)',
                borderRadius: '8px',
                fontSize: '14px',
                color: 'var(--text-primary)',
              }}
              formatter={(value) => [
                typeof value === 'number' ? value.toFixed(1) : '—',
                'RSI',
              ]}
            />
            {/* Overbought/Oversold zones */}
            <ReferenceLine y={70} stroke="var(--negative)" strokeDasharray="4 4" strokeOpacity={0.5} />
            <ReferenceLine y={30} stroke="var(--positive)" strokeDasharray="4 4" strokeOpacity={0.5} />
            <ReferenceLine y={50} stroke="var(--text-muted)" strokeDasharray="2 4" />

            <Area
              isAnimationActive={false}
              type="linear"
              dataKey="rsi"
              fill="var(--accent)"
              fillOpacity={0.1}
              stroke="none"
              connectNulls={false}
            />
            <Line
              isAnimationActive={false}
              type="linear"
              dataKey="rsi"
              stroke="var(--accent)"
              strokeWidth={1.5}
              dot={false}
              activeDot={{ r: 3, fill: 'var(--text-secondary)' }}
              connectNulls={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

export const TechnicalOverlayChart = memo(TechnicalOverlayChartComponent);
