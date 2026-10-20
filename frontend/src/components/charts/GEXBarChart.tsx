'use client';

import { memo, useMemo, useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer, Cell } from 'recharts';

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

function CustomTooltip({ active, payload }: {
  active?: boolean;
  payload?: Array<{ payload: GEXBarChartData }>;
}) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  return (
    <div className="rounded-lg border border-[var(--stroke)] bg-[var(--surface-raised)] px-3 py-2 text-sm text-[var(--text-primary)]">
      <p>Strike: ${point.strike.toLocaleString('en-US', { maximumFractionDigits: 2 })}</p>
      <p className={point.gex < 0 ? 'text-[var(--negative)]' : 'text-[var(--positive)]'}>
        {point.gexBillions >= 0 ? '+' : '−'}${Math.abs(point.gexBillions).toFixed(3)}B per 1% spot move
      </p>
    </div>
  );
}

function GEXBarChartComponent({ data, spotPrice, zeroGammaLevel, isLoading = false, height = 350 }: GEXBarChartProps) {
  const [range, setRange] = useState<'near' | 'full'>('near');
  const validSpot = Number.isFinite(spotPrice) && spotPrice > 0;
  const validZero = zeroGammaLevel != null && Number.isFinite(zeroGammaLevel) && zeroGammaLevel > 0;
  const fullData = useMemo(() => data
    .filter((point) => Number.isFinite(point.strike) && Number.isFinite(point.gex) && Number.isFinite(point.gexBillions))
    .sort((a, b) => a.strike - b.strike), [data]);
  const near = range === 'near' && validSpot;
  const chartData = near ? fullData.filter((point) => point.strike >= spotPrice * 0.98 && point.strike <= spotPrice * 1.02) : fullData;
  const levels = [...fullData.map((point) => point.strike), ...(validSpot ? [spotPrice] : []), ...(validZero ? [zeroGammaLevel] : [])];
  const minStrike = Math.min(...levels);
  const maxStrike = Math.max(...levels);
  const padding = Math.max((maxStrike - minStrike) * 0.02, 1);
  const xDomain = near ? [spotPrice * 0.98, spotPrice * 1.02] : [minStrike - padding, maxStrike + padding];
  const maxAbs = Math.max(...chartData.map((point) => Math.abs(point.gexBillions)), 0.1) * 1.1;
  const rawTickStep = maxAbs / 4;
  const tickMagnitude = 10 ** Math.floor(Math.log10(rawTickStep));
  const tickUnit = rawTickStep / tickMagnitude;
  const tickStep = (tickUnit <= 1 ? 1 : tickUnit <= 2 ? 2 : tickUnit <= 5 ? 5 : 10) * tickMagnitude;
  const tickCount = Math.floor(maxAbs / tickStep);
  const yTicks = Array.from({ length: 2 * tickCount + 1 }, (_, index) => (index - tickCount) * tickStep);
  const zeroOutsideView = validZero && (zeroGammaLevel < xDomain[0] || zeroGammaLevel > xDomain[1]);

  if (isLoading) return <div className="flex items-center justify-center text-sm text-[var(--text-secondary)]" style={{ height }}>Loading strike exposures…</div>;
  if (!fullData.length) return <div className="flex items-center justify-center text-sm text-[var(--text-secondary)]" style={{ height }}>No strike exposures available for this capture.</div>;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-[var(--text-secondary)]">Hedge notional per 1% spot move ($B)</p>
        <div role="group" aria-label="Strike range" className="flex gap-1 rounded-lg border border-[var(--stroke)] p-1">
          {(['near', 'full'] as const).map((option) => (
            <button key={option} type="button" aria-pressed={range === option} disabled={option === 'near' && !validSpot}
              onClick={() => setRange(option)}
              className={`rounded-md px-3 py-1.5 text-sm focus-visible:outline-2 focus-visible:outline-[var(--accent)] disabled:opacity-50 ${range === option ? 'bg-[var(--surface-raised)] text-[var(--text-primary)]' : 'text-[var(--text-secondary)] hover:bg-[var(--surface-raised)]'}`}>
              {option === 'near' ? 'Near spot ±2%' : 'Full chain'}
            </button>
          ))}
        </div>
      </div>
      <div className="flex flex-wrap gap-x-5 gap-y-1 text-sm tabular-nums">
        {validSpot && <span className="text-[var(--warning)]">Spot ${spotPrice.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} · solid line</span>}
        {validZero && <span className="text-[var(--accent)]">Zero gamma ${zeroGammaLevel.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}{zeroOutsideView ? ' · outside view' : ' · dashed line'}</span>}
      </div>
      {chartData.length ? (
        <ResponsiveContainer width="100%" height={height}>
          <BarChart data={chartData} margin={{ top: 20, right: 24, left: 8, bottom: 20 }} barSize={12}>
            <CartesianGrid stroke="var(--stroke)" vertical={false} />
            <XAxis dataKey="strike" type="number" domain={xDomain} allowDataOverflow
              tick={{ fill: 'var(--text-secondary)', fontSize: 12 }} tickLine={false} axisLine={{ stroke: 'var(--stroke)' }}
              tickFormatter={(value: number) => value.toLocaleString('en-US', { maximumFractionDigits: 2 })}
              label={{ value: 'Strike ($)', position: 'insideBottom', offset: -12, fill: 'var(--text-secondary)', fontSize: 12 }} />
            <YAxis domain={[-maxAbs, maxAbs]} ticks={yTicks} tick={{ fill: 'var(--text-secondary)', fontSize: 12 }} tickLine={false} axisLine={false}
              tickFormatter={(value: number) => `${value.toFixed(2)}B`} width={72} />
            <Tooltip content={<CustomTooltip />} isAnimationActive={false} />
            <ReferenceLine y={0} stroke="var(--text-muted)" />
            {validSpot && <ReferenceLine x={spotPrice} stroke="var(--warning)" strokeWidth={2} />}
            {validZero && !zeroOutsideView && <ReferenceLine x={zeroGammaLevel} stroke="var(--accent)" strokeWidth={2} strokeDasharray="6 4" />}
            <Bar dataKey="gexBillions" isAnimationActive={false} radius={[2, 2, 0, 0]}>
              {chartData.map((point) => <Cell key={point.strike} fill={point.gex < 0 ? 'var(--negative)' : 'var(--positive)'} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      ) : <div className="flex items-center justify-center text-sm text-[var(--text-secondary)]" style={{ height }}>No strikes in this range. Select Full chain to inspect available exposures.</div>}
      <p className="text-sm text-[var(--text-muted)]">{near ? 'Filtered to spot ±2%' : 'Full chain'} · {chartData.length} of {fullData.length} strikes · full-chain totals unchanged. Positive bars above zero; negative bars below zero.</p>
    </div>
  );
}

export const GEXBarChart = memo(GEXBarChartComponent);
