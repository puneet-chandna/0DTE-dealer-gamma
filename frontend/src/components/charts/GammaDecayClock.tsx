/**
 * GammaDecayClock — 0DTE Gamma Death Countdown.
 *
 * For 0DTE options, gamma explodes as T→0 then collapses to zero at expiry.
 * The last 90 minutes is the "danger zone" where gamma spikes violently.
 *
 * Shows:
 * - Circular countdown to 4:00 PM ET close
 * - Gamma intensity curve (1/√T decay)
 * - Danger zone highlighting
 * - Current gamma "fuel level"
 *
 * First-in-market: No tool visualizes the time-dimension of 0DTE gamma death.
 */

'use client';

import { memo, useMemo, useState, useEffect } from 'react';
import { cn } from '@/lib/utils';
import { Card, CardHeader, CardContent, CardTitle } from '@/components/ui';
import type { GEXSnapshot } from '@/types';

interface GammaDecayClockProps {
  data?: GEXSnapshot | null;
  isLoading?: boolean;
}

// Market close at 4:00 PM ET
const MARKET_CLOSE_HOUR = 16;
const MARKET_CLOSE_MINUTE = 0;
const MARKET_OPEN_HOUR = 9;
const MARKET_OPEN_MINUTE = 30;
const TOTAL_TRADING_MINUTES = (MARKET_CLOSE_HOUR * 60 + MARKET_CLOSE_MINUTE) - (MARKET_OPEN_HOUR * 60 + MARKET_OPEN_MINUTE); // 390 mins

function getMinutesUntilClose(): number {
  // Get current time in ET
  const now = new Date();
  const etString = now.toLocaleString('en-US', { timeZone: 'America/New_York' });
  const etDate = new Date(etString);

  const closeMinutes = MARKET_CLOSE_HOUR * 60 + MARKET_CLOSE_MINUTE;
  const currentMinutes = etDate.getHours() * 60 + etDate.getMinutes();

  return Math.max(0, closeMinutes - currentMinutes);
}

function getMinutesSinceOpen(): number {
  const now = new Date();
  const etString = now.toLocaleString('en-US', { timeZone: 'America/New_York' });
  const etDate = new Date(etString);

  const openMinutes = MARKET_OPEN_HOUR * 60 + MARKET_OPEN_MINUTE;
  const currentMinutes = etDate.getHours() * 60 + etDate.getMinutes();

  return Math.max(0, currentMinutes - openMinutes);
}

function formatTime(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

// Gamma intensity model: γ ∝ 1/√T for ATM options
function gammaIntensity(minutesRemaining: number): number {
  if (minutesRemaining <= 0) return 0;
  const T = minutesRemaining / TOTAL_TRADING_MINUTES; // normalized 0-1
  return Math.min(5, 1 / Math.sqrt(Math.max(T, 0.001))); // cap at 5x
}

function GammaDecayClockComponent({ data, isLoading }: GammaDecayClockProps) {
  const [minutesLeft, setMinutesLeft] = useState(getMinutesUntilClose);
  const [minutesElapsed, setMinutesElapsed] = useState(getMinutesSinceOpen);

  // Update every 30 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      setMinutesLeft(getMinutesUntilClose());
      setMinutesElapsed(getMinutesSinceOpen());
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  // Current gamma intensity
  const currentIntensity = useMemo(() => gammaIntensity(minutesLeft), [minutesLeft]);

  // Progress through trading day (0 to 1)
  const dayProgress = useMemo(
    () => Math.min(1, minutesElapsed / TOTAL_TRADING_MINUTES),
    [minutesElapsed]
  );

  // Danger zone: last 90 minutes
  const inDangerZone = minutesLeft <= 90 && minutesLeft > 0;
  const inCriticalZone = minutesLeft <= 30 && minutesLeft > 0;
  const marketClosed = minutesLeft <= 0 || minutesElapsed <= 0;

  // Decay curve data points (projected gamma for rest of day)
  const decayCurve = useMemo(() => {
    const points: { x: number; y: number; minutes: number }[] = [];
    // From market open to close, generate curve
    for (let m = 0; m <= TOTAL_TRADING_MINUTES; m += 5) {
      const remaining = TOTAL_TRADING_MINUTES - m;
      const intensity = gammaIntensity(remaining);
      points.push({
        x: (m / TOTAL_TRADING_MINUTES) * 100,
        y: intensity,
        minutes: m,
      });
    }
    return points;
  }, []);

  // Normalize curve for SVG
  const maxIntensity = useMemo(
    () => Math.max(...decayCurve.map((p) => p.y), 1),
    [decayCurve]
  );

  // Determine phase label and color
  const phase = useMemo(() => {
    if (marketClosed) return { label: 'MARKET CLOSED', color: 'text-zinc-500', bg: 'bg-zinc-800' };
    if (inCriticalZone) return { label: 'CRITICAL ZONE', color: 'text-rose-400', bg: 'bg-rose-900/50' };
    if (inDangerZone) return { label: 'DANGER ZONE', color: 'text-amber-400', bg: 'bg-amber-900/50' };
    if (minutesLeft <= 180) return { label: 'ELEVATED', color: 'text-orange-400', bg: 'bg-orange-900/40' };
    return { label: 'STABLE', color: 'text-emerald-400', bg: 'bg-emerald-900/40' };
  }, [minutesLeft, marketClosed, inDangerZone, inCriticalZone]);

  // Fuel gauge segments
  const fuelSegments = useMemo(() => {
    const segments = [];
    const totalSegs = 12;
    for (let i = 0; i < totalSegs; i++) {
      const segProgress = i / totalSegs;
      const isActive = segProgress <= dayProgress;
      const segMinutesLeft = TOTAL_TRADING_MINUTES * (1 - segProgress);
      const isDanger = segMinutesLeft <= 90;
      const isCritical = segMinutesLeft <= 30;
      segments.push({ isActive, isDanger, isCritical, index: i });
    }
    return segments;
  }, [dayProgress]);

  if (isLoading || !data) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Gamma Decay Clock</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-zinc-500">
            {isLoading ? 'Initializing countdown...' : 'Awaiting GEX data'}
          </p>
        </CardContent>
      </Card>
    );
  }

  // SVG decay curve path
  const curvePath = decayCurve
    .map((p, i) => {
      const x = 40 + (p.x / 100) * 510;
      const y = 130 - (p.y / maxIntensity) * 100;
      return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
    })
    .join(' ');

  // Filled area path
  const areaPath = curvePath + ` L ${40 + 510} 130 L 40 130 Z`;

  // Current position on curve
  const currentX = 40 + dayProgress * 510;

  return (
    <Card className={cn(
      inCriticalZone && 'border-rose-800/50',
      inDangerZone && !inCriticalZone && 'border-amber-800/30',
    )}>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>
            Gamma Decay Clock
          </CardTitle>
          <div className={cn('rounded-md px-2 py-0.5 text-xs font-bold', phase.bg, phase.color)}>
            {phase.label}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Top row: countdown + intensity + fuel gauge */}
        <div className="grid grid-cols-3 gap-4">
          {/* Countdown */}
          <div className="text-center">
            <p className="text-[10px] uppercase tracking-wider text-zinc-500">Time to Close</p>
            <p
              className={cn(
                'mt-1 text-2xl font-black tabular-nums',
                inCriticalZone
                  ? 'text-rose-400'
                  : inDangerZone
                    ? 'text-amber-400'
                    : 'text-zinc-200'
              )}
              style={inCriticalZone ? {
                animation: 'pulse 1s ease-in-out infinite',
              } : undefined}
            >
              {marketClosed ? '--:--' : formatTime(minutesLeft)}
            </p>
          </div>

          {/* Gamma Intensity */}
          <div className="text-center">
            <p className="text-[10px] uppercase tracking-wider text-zinc-500">γ Intensity</p>
            <p
              className={cn(
                'mt-1 text-2xl font-black tabular-nums',
                currentIntensity > 3
                  ? 'text-rose-400'
                  : currentIntensity > 2
                    ? 'text-amber-400'
                    : currentIntensity > 1.2
                      ? 'text-orange-400'
                      : 'text-emerald-400'
              )}
            >
              {marketClosed ? '0.00' : currentIntensity.toFixed(2)}×
            </p>
          </div>

          {/* Net GEX context */}
          <div className="text-center">
            <p className="text-[10px] uppercase tracking-wider text-zinc-500">Net GEX</p>
            <p
              className={cn(
                'mt-1 text-2xl font-black tabular-nums',
                data.net_gex > 0 ? 'text-emerald-400' : 'text-rose-400'
              )}
            >
              {(data.net_gex / 1e9).toFixed(2)}B
            </p>
          </div>
        </div>

        {/* Fuel gauge */}
        <div className="flex items-center gap-1">
          <span className="text-[9px] text-zinc-600 w-8">9:30</span>
          <div className="flex flex-1 gap-0.5">
            {fuelSegments.map((seg) => (
              <div
                key={seg.index}
                className={cn(
                  'h-3 flex-1 rounded-sm transition-all duration-300',
                  !seg.isActive
                    ? seg.isCritical
                      ? 'bg-rose-900/20'
                      : seg.isDanger
                        ? 'bg-amber-900/15'
                        : 'bg-zinc-800/40'
                    : seg.isCritical
                      ? 'bg-rose-500'
                      : seg.isDanger
                        ? 'bg-amber-500'
                        : 'bg-emerald-500/70'
                )}
              />
            ))}
          </div>
          <span className="text-[9px] text-zinc-600 w-8 text-right">4:00</span>
        </div>

        {/* Decay Curve */}
        <div className="relative">
          <svg viewBox="0 0 600 155" className="w-full" style={{ height: '140px' }}>
            {/* Background */}
            <rect x="40" y="20" width="510" height="110" fill="transparent" />

            {/* Y-axis labels */}
            <text x="35" y="35" textAnchor="end" fill="#52525b" fontSize="8">5×</text>
            <text x="35" y="57" textAnchor="end" fill="#52525b" fontSize="8">4×</text>
            <text x="35" y="79" textAnchor="end" fill="#52525b" fontSize="8">3×</text>
            <text x="35" y="101" textAnchor="end" fill="#52525b" fontSize="8">2×</text>
            <text x="35" y="125" textAnchor="end" fill="#52525b" fontSize="8">1×</text>

            {/* Grid lines */}
            {[30, 52, 74, 96, 118].map((y, i) => (
              <line key={i} x1="40" y1={y} x2="550" y2={y} stroke="#1c1c1e" strokeWidth="0.5" />
            ))}

            {/* Danger zone background (last 90 min = last 23% of day) */}
            <rect
              x={40 + (1 - 90 / TOTAL_TRADING_MINUTES) * 510}
              y="20"
              width={(90 / TOTAL_TRADING_MINUTES) * 510}
              height="110"
              fill="#7f1d1d"
              opacity="0.12"
            />
            {/* Critical zone (last 30 min) */}
            <rect
              x={40 + (1 - 30 / TOTAL_TRADING_MINUTES) * 510}
              y="20"
              width={(30 / TOTAL_TRADING_MINUTES) * 510}
              height="110"
              fill="#991b1b"
              opacity="0.15"
            />

            {/* Filled area under curve */}
            <path d={areaPath} fill="url(#decayGradient)" opacity="0.3" />

            {/* Decay curve line */}
            <path
              d={curvePath}
              fill="none"
              stroke="url(#curveGradient)"
              strokeWidth="2"
              strokeLinecap="round"
            />

            {/* Gradients */}
            <defs>
              <linearGradient id="decayGradient" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="#10b981" stopOpacity="0.2" />
                <stop offset="70%" stopColor="#f59e0b" stopOpacity="0.3" />
                <stop offset="90%" stopColor="#ef4444" stopOpacity="0.5" />
                <stop offset="100%" stopColor="#ef4444" stopOpacity="0.1" />
              </linearGradient>
              <linearGradient id="curveGradient" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="#10b981" />
                <stop offset="65%" stopColor="#f59e0b" />
                <stop offset="85%" stopColor="#ef4444" />
                <stop offset="100%" stopColor="#991b1b" />
              </linearGradient>
            </defs>

            {/* Current position marker */}
            {!marketClosed && (
              <g>
                <line
                  x1={currentX}
                  y1="20"
                  x2={currentX}
                  y2="130"
                  stroke="#fbbf24"
                  strokeWidth="1"
                  strokeDasharray="4 3"
                  opacity="0.6"
                />
                <circle
                  cx={currentX}
                  cy={130 - (currentIntensity / maxIntensity) * 100}
                  r="4"
                  fill="#fbbf24"
                  stroke="#fbbf24"
                  strokeWidth="1"
                >
                  <animate
                    attributeName="r"
                    values="4;6;4"
                    dur={inDangerZone ? '0.8s' : '2s'}
                    repeatCount="indefinite"
                  />
                </circle>
                <text
                  x={currentX}
                  y="145"
                  textAnchor="middle"
                  fill="#fbbf24"
                  fontSize="8"
                  fontWeight="bold"
                >
                  NOW
                </text>
              </g>
            )}

            {/* Zone labels */}
            <text
              x={40 + (1 - 90 / TOTAL_TRADING_MINUTES) * 510 + 2}
              y="28"
              fill="#f59e0b"
              fontSize="7"
              opacity="0.5"
            >
              DANGER
            </text>
            <text
              x={40 + (1 - 30 / TOTAL_TRADING_MINUTES) * 510 + 2}
              y="28"
              fill="#ef4444"
              fontSize="7"
              opacity="0.5"
            >
              CRITICAL
            </text>

            {/* X-axis time labels */}
            <text x="40" y="152" fill="#52525b" fontSize="7">9:30</text>
            <text x={40 + 510 * 0.25} y="152" fill="#52525b" fontSize="7">11:08</text>
            <text x={40 + 510 * 0.5} y="152" fill="#52525b" fontSize="7">12:45</text>
            <text x={40 + 510 * 0.75} y="152" fill="#52525b" fontSize="7">2:23</text>
            <text x="538" y="152" fill="#52525b" fontSize="7">4:00</text>
          </svg>
        </div>

        {/* Footer explanation */}
        <p className="text-[10px] text-zinc-600">
          Gamma ∝ 1/√T — intensity explodes as 0DTE options approach expiry, then dies to zero.
          {inDangerZone
            ? ' You are in the danger zone. Gamma is elevated.'
            : ' The curve shows projected gamma intensity for the rest of the trading day.'}
        </p>
      </CardContent>
    </Card>
  );
}

export const GammaDecayClock = memo(GammaDecayClockComponent);
