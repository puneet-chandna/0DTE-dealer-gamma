/**
 * GammaMagnetField — Physics-based price attraction visualization.
 *
 * Positive GEX strikes = attractors (dealers hedge AGAINST movement → price pulled back)
 * Negative GEX strikes = repellers (dealers hedge WITH movement → price pushed away)
 * Force ∝ |GEX| / distance²
 *
 * First-in-market: No other platform visualizes dealer positioning as gravitational fields.
 */

'use client';

import { memo, useMemo } from 'react';
import { cn } from '@/lib/utils';
import { Card, CardHeader, CardContent, CardTitle } from '@/components/ui';
import type { GEXSnapshot } from '@/types';

interface GammaMagnetFieldProps {
  data?: GEXSnapshot | null;
  isLoading?: boolean;
}

interface StrikeField {
  strike: number;
  gex: number;
  normalizedGex: number; // -1 to +1
  distanceFromSpot: number; // in points
  xPosition: number; // 0-100% across SVG
  force: number; // attraction/repulsion magnitude
  isAttractor: boolean; // positive GEX = attractor
}

function formatBillions(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1e9) return `${(value / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${(value / 1e6).toFixed(0)}M`;
  if (abs >= 1e3) return `${(value / 1e3).toFixed(0)}K`;
  return value.toFixed(0);
}

function GammaMagnetFieldComponent({ data, isLoading }: GammaMagnetFieldProps) {
  const fields = useMemo((): StrikeField[] => {
    if (!data?.gex_by_strike || !data.spot_price) return [];

    const entries = Object.entries(data.gex_by_strike)
      .map(([strike, gex]) => ({ strike: Number(strike), gex: Number(gex) }))
      .filter((e) => Math.abs(e.gex) > 0 && isFinite(e.gex))
      .sort((a, b) => a.strike - b.strike);

    if (entries.length === 0) return [];

    const maxGex = Math.max(...entries.map((e) => Math.abs(e.gex)), 1);
    const minStrike = entries[0].strike;
    const maxStrike = entries[entries.length - 1].strike;
    const strikeRange = maxStrike - minStrike || 1;

    return entries.map((e) => {
      const distanceFromSpot = Math.abs(e.strike - data.spot_price);
      const normalizedGex = e.gex / maxGex; // -1 to +1
      // Force: |GEX| / (distance² + dampening) — capped for vis
      const force = Math.abs(e.gex) / (Math.pow(distanceFromSpot + 5, 1.5) + 1e6);

      return {
        strike: e.strike,
        gex: e.gex,
        normalizedGex,
        distanceFromSpot,
        xPosition: ((e.strike - minStrike) / strikeRange) * 100,
        force,
        isAttractor: e.gex > 0, // Positive GEX = long gamma = mean-reversion = attraction
      };
    });
  }, [data]);

  // Net force direction: where is price being pulled?
  const netForce = useMemo(() => {
    if (!data?.spot_price || fields.length === 0) return { direction: 0, target: 0, label: '' };

    let weightedPull = 0;
    let totalWeight = 0;

    for (const f of fields) {
      if (f.isAttractor) {
        const pull = f.gex / Math.pow(f.distanceFromSpot + 5, 1.5);
        weightedPull += f.strike * Math.abs(pull);
        totalWeight += Math.abs(pull);
      }
    }

    const target = totalWeight > 0 ? weightedPull / totalWeight : data.spot_price;
    const direction = target - data.spot_price;

    let label = 'Balanced';
    if (Math.abs(direction) > 10) {
      label = direction > 0 ? `Pull toward ${target.toFixed(0)}` : `Pull toward ${target.toFixed(0)}`;
    }

    return { direction, target, label };
  }, [data, fields]);

  // Spot position within the field
  const spotX = useMemo(() => {
    if (!data?.spot_price || fields.length === 0) return 50;
    const strikes = fields.map((f) => f.strike);
    const min = Math.min(...strikes);
    const max = Math.max(...strikes);
    const range = max - min || 1;
    return ((data.spot_price - min) / range) * 100;
  }, [data, fields]);

  // Top attractors and repellers
  const topFields = useMemo(() => {
    const sorted = [...fields].sort((a, b) => Math.abs(b.gex) - Math.abs(a.gex));
    return sorted.slice(0, 5);
  }, [fields]);

  if (isLoading || !data) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Gamma Magnet Field</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-zinc-500">
            {isLoading ? 'Computing gravitational fields...' : 'Awaiting GEX data'}
          </p>
        </CardContent>
      </Card>
    );
  }

  const hasData = fields.length > 0;

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle>
            Gamma Magnet Field
          </CardTitle>
          {hasData && (
            <div
              className={cn(
                'rounded-md px-2 py-0.5 text-xs font-medium',
                netForce.direction > 5
                  ? 'bg-emerald-900/50 text-emerald-300'
                  : netForce.direction < -5
                    ? 'bg-rose-900/50 text-rose-300'
                    : 'bg-zinc-800 text-zinc-400'
              )}
            >
              {netForce.label}
            </div>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {hasData ? (
          <>
            {/* SVG Force Field */}
            <div className="relative">
              <svg
                viewBox="0 0 600 200"
                className="w-full"
                style={{ height: '180px' }}
              >
                <defs>
                  {/* Glow filters */}
                  <filter id="glow-cyan" x="-50%" y="-50%" width="200%" height="200%">
                    <feGaussianBlur stdDeviation="4" result="blur" />
                    <feMerge>
                      <feMergeNode in="blur" />
                      <feMergeNode in="SourceGraphic" />
                    </feMerge>
                  </filter>
                  <filter id="glow-magenta" x="-50%" y="-50%" width="200%" height="200%">
                    <feGaussianBlur stdDeviation="4" result="blur" />
                    <feMerge>
                      <feMergeNode in="blur" />
                      <feMergeNode in="SourceGraphic" />
                    </feMerge>
                  </filter>
                  <filter id="glow-spot" x="-50%" y="-50%" width="200%" height="200%">
                    <feGaussianBlur stdDeviation="6" result="blur" />
                    <feMerge>
                      <feMergeNode in="blur" />
                      <feMergeNode in="SourceGraphic" />
                    </feMerge>
                  </filter>

                  {/* Radial gradients for gravity wells */}
                  <radialGradient id="attractor-gradient">
                    <stop offset="0%" stopColor="#06b6d4" stopOpacity="0.7" />
                    <stop offset="50%" stopColor="#06b6d4" stopOpacity="0.2" />
                    <stop offset="100%" stopColor="#06b6d4" stopOpacity="0" />
                  </radialGradient>
                  <radialGradient id="repeller-gradient">
                    <stop offset="0%" stopColor="#ec4899" stopOpacity="0.7" />
                    <stop offset="50%" stopColor="#ec4899" stopOpacity="0.2" />
                    <stop offset="100%" stopColor="#ec4899" stopOpacity="0" />
                  </radialGradient>
                </defs>

                {/* Background grid */}
                {Array.from({ length: 13 }, (_, i) => (
                  <line
                    key={`vgrid-${i}`}
                    x1={30 + i * 45}
                    y1={20}
                    x2={30 + i * 45}
                    y2={180}
                    stroke="#27272a"
                    strokeWidth="0.5"
                  />
                ))}
                {Array.from({ length: 5 }, (_, i) => (
                  <line
                    key={`hgrid-${i}`}
                    x1={30}
                    y1={20 + i * 40}
                    x2={570}
                    y2={20 + i * 40}
                    stroke="#27272a"
                    strokeWidth="0.5"
                  />
                ))}

                {/* Gravity wells / repulsion zones */}
                {fields.map((f, i) => {
                  const cx = 30 + (f.xPosition / 100) * 540;
                  const cy = 100; // center line
                  const radius = Math.max(8, Math.min(40, Math.abs(f.normalizedGex) * 40));
                  const opacity = Math.max(0.15, Math.min(0.8, Math.abs(f.normalizedGex)));
                  const pulseDuration = `${2 + (i % 4) * 0.35}s`;

                  return (
                    <g key={`field-${i}`}>
                      {/* Gravity well circle */}
                      <circle
                        cx={cx}
                        cy={cy}
                        r={radius}
                        fill={`url(#${f.isAttractor ? 'attractor' : 'repeller'}-gradient)`}
                        opacity={opacity}
                      >
                        <animate
                          attributeName="r"
                          values={`${radius};${radius * 1.15};${radius}`}
                          dur={pulseDuration}
                          repeatCount="indefinite"
                        />
                      </circle>

                      {/* Core dot */}
                      <circle
                        cx={cx}
                        cy={cy}
                        r={Math.max(2, radius * 0.2)}
                        fill={f.isAttractor ? '#06b6d4' : '#ec4899'}
                        filter={f.isAttractor ? 'url(#glow-cyan)' : 'url(#glow-magenta)'}
                        opacity={0.9}
                      />

                      {/* Field lines (concentric rings for strong fields) */}
                      {Math.abs(f.normalizedGex) > 0.3 && (
                        <circle
                          cx={cx}
                          cy={cy}
                          r={radius * 1.6}
                          fill="none"
                          stroke={f.isAttractor ? '#06b6d4' : '#ec4899'}
                          strokeWidth="0.5"
                          strokeDasharray="3 3"
                          opacity={0.2}
                        >
                          <animate
                            attributeName="r"
                            values={`${radius * 1.4};${radius * 1.8};${radius * 1.4}`}
                            dur="3s"
                            repeatCount="indefinite"
                          />
                        </circle>
                      )}
                    </g>
                  );
                })}

                {/* Zero Gamma Level */}
                {data.zero_gamma_level > 0 && (() => {
                  const strikes = fields.map((f) => f.strike);
                  const min = Math.min(...strikes);
                  const max = Math.max(...strikes);
                  const range = max - min || 1;
                  const zglX = 30 + ((data.zero_gamma_level - min) / range) * 540;
                  if (zglX >= 30 && zglX <= 570) {
                    return (
                      <g>
                        <line
                          x1={zglX}
                          y1={20}
                          x2={zglX}
                          y2={180}
                          stroke="#a78bfa"
                          strokeWidth="1"
                          strokeDasharray="6 4"
                          opacity={0.5}
                        />
                        <text x={zglX} y={16} textAnchor="middle" fill="#a78bfa" fontSize="8" opacity="0.7">
                          0Γ
                        </text>
                      </g>
                    );
                  }
                  return null;
                })()}

                {/* Spot price indicator */}
                {(() => {
                  const sx = 30 + (spotX / 100) * 540;
                  return (
                    <g>
                      {/* Spot vertical line */}
                      <line
                        x1={sx}
                        y1={30}
                        x2={sx}
                        y2={170}
                        stroke="#fbbf24"
                        strokeWidth="1.5"
                        opacity={0.6}
                      />
                      {/* Spot dot */}
                      <circle
                        cx={sx}
                        cy={100}
                        r={5}
                        fill="#fbbf24"
                        filter="url(#glow-spot)"
                      >
                        <animate
                          attributeName="r"
                          values="5;7;5"
                          dur="1.5s"
                          repeatCount="indefinite"
                        />
                      </circle>
                      {/* Spot label */}
                      <text
                        x={sx}
                        y={190}
                        textAnchor="middle"
                        fill="#fbbf24"
                        fontSize="9"
                        fontWeight="bold"
                      >
                        SPOT {data.spot_price.toFixed(0)}
                      </text>

                      {/* Net force arrow */}
                      {Math.abs(netForce.direction) > 3 && (
                        <g>
                          <line
                            x1={sx}
                            y1={100}
                            x2={sx + Math.sign(netForce.direction) * Math.min(80, Math.abs(netForce.direction))}
                            y2={100}
                            stroke="#fbbf24"
                            strokeWidth="2"
                            markerEnd="url(#arrowhead)"
                            opacity={0.8}
                          >
                            <animate
                              attributeName="opacity"
                              values="0.5;1;0.5"
                              dur="2s"
                              repeatCount="indefinite"
                            />
                          </line>
                        </g>
                      )}
                    </g>
                  );
                })()}

                {/* Arrow marker */}
                <defs>
                  <marker
                    id="arrowhead"
                    markerWidth="8"
                    markerHeight="6"
                    refX="8"
                    refY="3"
                    orient="auto"
                  >
                    <polygon points="0 0, 8 3, 0 6" fill="#fbbf24" />
                  </marker>
                </defs>
              </svg>
            </div>

            {/* Legend */}
            <div className="flex flex-wrap items-center justify-center gap-3 text-[10px] text-zinc-500 sm:gap-6">
              <div className="flex items-center gap-1.5">
                <div className="h-2 w-2 rounded-full bg-cyan-500" />
                <span>Attractor (Long γ)</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="h-2 w-2 rounded-full bg-pink-500" />
                <span>Repeller (Short γ)</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="h-2 w-2 rounded-full bg-amber-400" />
                <span>Spot Price</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="h-1 w-3 border-t border-dashed border-violet-400" />
                <span>Zero Gamma</span>
              </div>
            </div>

            {/* Top gravity wells table */}
            <div className="mt-2">
              <p className="mb-2 text-[10px] font-medium uppercase tracking-wider text-zinc-500">
                Strongest Fields
              </p>
              <div className="grid grid-cols-2 gap-1 text-center sm:grid-cols-3 lg:grid-cols-5">
                {topFields.map((f, i) => (
                  <div
                    key={i}
                    className={cn(
                      'rounded-md px-1.5 py-1.5 text-xs',
                      f.isAttractor
                        ? 'bg-cyan-950/40 text-cyan-300'
                        : 'bg-pink-950/40 text-pink-300'
                    )}
                  >
                    <div className="font-bold tabular-nums">{f.strike.toFixed(0)}</div>
                    <div className="text-[9px] opacity-70">${formatBillions(f.gex)}</div>
                  </div>
                ))}
              </div>
            </div>
          </>
        ) : (
          <p className="text-sm text-zinc-500">No strike data available</p>
        )}
      </CardContent>
    </Card>
  );
}

export const GammaMagnetField = memo(GammaMagnetFieldComponent);
