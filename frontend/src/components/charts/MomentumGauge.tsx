/**
 * MomentumGauge - Hawkes-Style Flow Intensity Gauge
 *
 * Snapshot-based excitation proxy from volume/open-interest deltas:
 * - Left (red): Put flow dominance
 * - Center (neutral): Balanced flow
 * - Right (green): Call flow dominance
 */

'use client';

import { memo, useMemo } from 'react';
import { cn } from '@/lib/utils';
import { Card, CardHeader, CardContent, CardTitle } from '@/components/ui';
import type { HawkesState } from '@/types';

interface MomentumGaugeProps {
  data?: HawkesState | null;
  isLoading?: boolean;
}

function getProviderModeLabel(providerMode?: HawkesState['provider_mode']) {
  if (providerMode === 'tradier_rich') return 'Tradier-Rich Mode';
  if (providerMode === 'yfinance_proxy') return 'YFinance Proxy Mode';
  return 'Snapshot Proxy Mode';
}

function MomentumGaugeComponent({ data, isLoading }: MomentumGaugeProps) {
  // Map net_toxicity to -100..+100 angle range
  const gaugeAngle = useMemo(() => {
    if (!data) return 0;
    // Clamp net_toxicity to reasonable range and normalize
    const maxIntensity = Math.max(
      Math.abs(data.call_intensity),
      Math.abs(data.put_intensity),
      0.001
    );
    const normalized = data.net_toxicity / maxIntensity; // -1 to +1
    return normalized * 90; // -90 to +90 degrees
  }, [data]);

  const squeezePercent = data && Number.isFinite(data.squeeze_score) ? Math.round(data.squeeze_score * 100) : 0;
  const isHighSqueeze = squeezePercent >= 60;
  const baselineReady = data?.baseline_ready ?? false;
  const confidenceScore = data?.confidence_score;
  const confidenceLabel = `Heuristic confidence: ${typeof confidenceScore === 'number' && Number.isFinite(confidenceScore) ? `${Math.round(confidenceScore * 100)} / 100` : 'unavailable'}`;
  const providerModeLabel = getProviderModeLabel(data?.provider_mode);

  if (isLoading || !data) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Hawkes-Style Flow Intensity</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-[var(--text-secondary)]">
            {isLoading ? 'Analyzing snapshot flow...' : 'Awaiting Hawkes-style data'}
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div
            className="space-y-1"
            title="Snapshot-based excitation proxy from consecutive volume and open-interest changes."
          >
            <CardTitle>
              Hawkes-Style Flow Intensity
            </CardTitle>
            <p className="text-sm text-[var(--text-secondary)]">
              Snapshot-based excitation proxy from volume/OI changes.
            </p>
          </div>
          {isHighSqueeze && (
            <div className="rounded-md bg-amber-900/60 px-2 py-0.5 text-sm font-bold text-amber-300">
              Squeeze score {squeezePercent} / 100
            </div>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {/* Gauge */}
        <div className="relative mx-auto flex h-40 w-64 items-end justify-center overflow-hidden">
          {/* Background arc */}
          <svg role="img" aria-label={`Snapshot intensity balance: calls ${data.call_intensity.toFixed(2)}, puts ${data.put_intensity.toFixed(2)}`} viewBox="0 0 200 110" className="absolute inset-0 h-full w-full">
            {/* Background arc */}
            <path
              d="M 15 100 A 85 85 0 0 1 185 100"
              fill="none"
              stroke="var(--stroke)"
              strokeWidth="12"
              strokeLinecap="round"
            />

            {/* Tick marks */}
            {[-90, -60, -30, 0, 30, 60, 90].map((angle) => {
              const rad = ((angle - 90) * Math.PI) / 180;
              const innerR = 73;
              const outerR = 80;
              const cx = 100;
              const cy = 100;
              return (
                <line
                  key={angle}
                  x1={cx + innerR * Math.cos(rad)}
                  y1={cy + innerR * Math.sin(rad)}
                  x2={cx + outerR * Math.cos(rad)}
                  y2={cy + outerR * Math.sin(rad)}
                  stroke="var(--text-secondary)"
                  strokeWidth="1.5"
                />
              );
            })}

            {/* Needle */}
            <g transform={`rotate(${gaugeAngle}, 100, 100)`}>
              <line
                x1="100"
                y1="100"
                x2="100"
                y2="25"
                stroke="var(--text-primary)"
                strokeWidth="2.5"
                strokeLinecap="round"
              />
              <circle cx="100" cy="100" r="4" fill="var(--text-primary)" />
            </g>
          </svg>

          {/* Labels */}
          <div className="absolute bottom-0 flex w-full justify-between px-2 text-sm text-[var(--text-secondary)]">
            <span className="text-[var(--negative)]">PUT</span>
            <span className="text-[var(--positive)]">CALL</span>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <span
            className={cn(
              'rounded-full border px-2.5 py-1 text-sm font-medium',
              'border-zinc-700 bg-zinc-900 text-zinc-300'
            )}
          >
            {confidenceLabel}
          </span>
          <span className="rounded-full border border-zinc-700 bg-zinc-900/80 px-2.5 py-1 text-sm font-medium text-[var(--text-primary)]">
            {providerModeLabel}
          </span>
          <span
            className={cn(
              'rounded-full border px-2.5 py-1 text-sm font-medium',
              baselineReady
                ? 'border-sky-500/30 bg-sky-500/10 text-sky-300'
                : 'border-amber-500/30 bg-amber-500/10 text-amber-300'
            )}
          >
            {baselineReady ? 'Baseline Ready' : 'Baselining'}
          </span>
        </div>

        <p className="mt-3 text-sm leading-5 text-[var(--text-secondary)]">
          {baselineReady
            ? `${data.event_count ?? 0} changed contracts counted from consecutive snapshots; these are not trades.`
            : 'Building flow baseline from consecutive snapshots before new contracts contribute to the signal.'}
        </p>

        {/* Metrics row */}
        <div className="mt-4 grid grid-cols-3 gap-2 text-center">
          <div>
            <p className="text-sm uppercase tracking-wider text-[var(--text-secondary)]">Put Intensity</p>
            <p className="text-sm font-bold tabular-nums text-[var(--negative)]">
              {data.put_intensity.toFixed(2)}
            </p>
          </div>
          <div>
            <p className="text-sm uppercase tracking-wider text-[var(--text-secondary)]">Squeeze Score</p>
            <p
              className={cn(
                'text-sm font-bold tabular-nums',
                isHighSqueeze ? 'text-amber-400' : 'text-[var(--text-primary)]'
              )}
            >
              {squeezePercent} / 100
            </p>
          </div>
          <div>
            <p className="text-sm uppercase tracking-wider text-[var(--text-secondary)]">Call Intensity</p>
            <p className="text-sm font-bold tabular-nums text-[var(--positive)]">
              {data.call_intensity.toFixed(2)}
            </p>
          </div>
        </div>
        <p className="mt-2 text-center text-sm text-[var(--text-secondary)]">Uncalibrated snapshot heuristic; this score is not a probability.</p>
      </CardContent>
    </Card>
  );
}

export const MomentumGauge = memo(MomentumGaugeComponent);
