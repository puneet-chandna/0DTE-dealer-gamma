'use client';

import { memo, useMemo } from 'react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';
import { formatMarketTimestamp } from '@/lib/utils';

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
interface PlottedCapture {
  time: number;
  netGexBillions: number | null;
}

function TimeSeriesChartComponent({ data, isLoading = false, height = 250, showZeroLine = true }: TimeSeriesChartProps) {
  const chartData = useMemo(() => {
    const captures = data.map((point) => ({ time: Date.parse(point.timestamp), netGexBillions: point.netGexBillions }))
      .filter((point) => Number.isFinite(point.time) && Number.isFinite(point.netGexBillions))
      .sort((a, b) => a.time - b.time);
    const plotted: PlottedCapture[] = [];
    captures.forEach((point, index) => {
      const previous = captures[index - 1];
      // A null separates capture segments without inventing a market observation.
      if (previous && point.time - previous.time > 5 * 60_000) {
        plotted.push({ time: previous.time + (point.time - previous.time) / 2, netGexBillions: null });
      }
      plotted.push(point);
    });
    return plotted;
  }, [data]);
  const showSeconds = chartData.length > 0 && chartData[chartData.length - 1].time - chartData[0].time < 5 * 60_000;
  const maxAbs = Math.max(...chartData.map((point) => Math.abs(point.netGexBillions ?? 0)), 0.5) * 1.15;

  if (isLoading) return <div className="flex items-center justify-center text-sm text-[var(--text-secondary)]" style={{ height }}>Loading capture history…</div>;
  if (!chartData.length) return <div className="flex items-center justify-center text-sm text-[var(--text-secondary)]" style={{ height }}>No capture history available.</div>;

  return (
    <div className="space-y-2">
      <ResponsiveContainer width="100%" height={height}>
        <AreaChart data={chartData} margin={{ top: 10, right: 24, left: 8, bottom: 20 }}>
          <CartesianGrid stroke="var(--stroke)" vertical={false} />
          <XAxis dataKey="time" type="number" scale="time" domain={['dataMin', 'dataMax']}
            tick={{ fill: 'var(--text-secondary)', fontSize: 12 }} tickLine={false} axisLine={{ stroke: 'var(--stroke)' }}
            tickFormatter={(value: number) => new Date(value).toLocaleTimeString('en-US', { timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', second: showSeconds ? '2-digit' : undefined, hour12: false })}
            label={{ value: 'Capture time (ET)', position: 'insideBottom', offset: -12, fill: 'var(--text-secondary)', fontSize: 12 }} />
          <YAxis domain={[-maxAbs, maxAbs]} tick={{ fill: 'var(--text-secondary)', fontSize: 12 }} tickLine={false} axisLine={false}
            tickFormatter={(value: number) => `${value.toFixed(1)}B`} width={64} />
          <Tooltip isAnimationActive={false} contentStyle={{ backgroundColor: 'var(--surface-raised)', border: '1px solid var(--stroke)', color: 'var(--text-primary)', fontSize: 14 }}
            labelFormatter={(value) => formatMarketTimestamp(new Date(Number(value)).toISOString()) ?? ''}
            formatter={(value) => [`${Number(value) >= 0 ? '+' : '−'}$${Math.abs(Number(value)).toFixed(3)}B per 1% spot move`, 'Net GEX']} />
          {showZeroLine && <ReferenceLine y={0} stroke="var(--text-muted)" />}
          <Area type="linear" dataKey="netGexBillions" stroke="var(--accent)" strokeWidth={2} fill="var(--accent)" fillOpacity={0.08}
            connectNulls={false} isAnimationActive={false} dot={{ r: 2, fill: 'var(--accent)' }} activeDot={{ r: 4 }} />
        </AreaChart>
      </ResponsiveContainer>
      <p className="text-sm text-[var(--text-muted)]">Net hedge notional per 1% spot move ($B). Elapsed time is to scale; gaps over 5 minutes are left unconnected. Points use the source and data kind identified above.</p>
    </div>
  );
}

export const TimeSeriesChart = memo(TimeSeriesChartComponent);
