/**
 * MomentumGauge - Hawkes Process Order Flow Toxicity Gauge
 *
 * A semicircular gauge showing the momentum/toxicity of order flow.
 * Driven by the Hawkes process intensity values:
 * - Left (red): Put toxicity dominant
 * - Center (neutral): Balanced flow
 * - Right (green): Call toxicity dominant
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

  const squeezePercent = data ? Math.round(data.squeeze_probability * 100) : 0;
  const isHighSqueeze = squeezePercent >= 60;

  if (isLoading || !data) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Order Flow Momentum</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-zinc-500">
            {isLoading ? 'Analyzing order flow...' : 'Awaiting Hawkes data'}
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Order Flow Momentum</CardTitle>
          {isHighSqueeze && (
            <div className="animate-pulse rounded-md bg-amber-900/60 px-2 py-0.5 text-xs font-bold text-amber-300">
              ⚡ SQUEEZE {squeezePercent}%
            </div>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {/* Gauge */}
        <div className="relative mx-auto flex h-40 w-64 items-end justify-center overflow-hidden">
          {/* Background arc */}
          <svg viewBox="0 0 200 110" className="absolute inset-0 h-full w-full">
            {/* Gradient arc background */}
            <defs>
              <linearGradient id="gaugeGradient" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="#f43f5e" stopOpacity="0.6" />
                <stop offset="35%" stopColor="#f97316" stopOpacity="0.3" />
                <stop offset="50%" stopColor="#3b82f6" stopOpacity="0.2" />
                <stop offset="65%" stopColor="#f97316" stopOpacity="0.3" />
                <stop offset="100%" stopColor="#10b981" stopOpacity="0.6" />
              </linearGradient>
            </defs>

            {/* Background arc */}
            <path
              d="M 15 100 A 85 85 0 0 1 185 100"
              fill="none"
              stroke="url(#gaugeGradient)"
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
                  stroke="#52525b"
                  strokeWidth="1.5"
                />
              );
            })}

            {/* Needle */}
            <g
              transform={`rotate(${gaugeAngle}, 100, 100)`}
              className="transition-transform duration-700 ease-out"
            >
              <line
                x1="100"
                y1="100"
                x2="100"
                y2="25"
                stroke="#f4f4f5"
                strokeWidth="2.5"
                strokeLinecap="round"
              />
              <circle cx="100" cy="100" r="4" fill="#f4f4f5" />
            </g>
          </svg>

          {/* Labels */}
          <div className="absolute bottom-0 flex w-full justify-between px-2 text-[10px] text-zinc-500">
            <span className="text-rose-400/70">PUT</span>
            <span className="text-emerald-400/70">CALL</span>
          </div>
        </div>

        {/* Metrics row */}
        <div className="mt-4 grid grid-cols-3 gap-2 text-center">
          <div>
            <p className="text-[10px] uppercase tracking-wider text-zinc-500">Put Intensity</p>
            <p className="text-sm font-bold tabular-nums text-rose-400">
              {data.put_intensity.toFixed(2)}
            </p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-wider text-zinc-500">Squeeze Prob</p>
            <p
              className={cn(
                'text-sm font-bold tabular-nums',
                isHighSqueeze ? 'text-amber-400' : 'text-zinc-300'
              )}
            >
              {squeezePercent}%
            </p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-wider text-zinc-500">Call Intensity</p>
            <p className="text-sm font-bold tabular-nums text-emerald-400">
              {data.call_intensity.toFixed(2)}
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export const MomentumGauge = memo(MomentumGaugeComponent);
