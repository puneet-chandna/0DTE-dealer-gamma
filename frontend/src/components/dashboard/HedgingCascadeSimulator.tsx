/**
 * HedgingCascadeSimulator — Interactive "What-If" Feedback Loop Visualizer.
 *
 * The user drags a slider to a hypothetical spot price. The simulator shows:
 * 1. Initial move → delta change across all strikes
 * 2. Dealer hedging → market impact
 * 3. Further price movement → more hedging → cascade
 *
 * This is the feedback loop that causes flash crashes and gamma squeezes.
 * First-in-market: No platform lets you interactively simulate dealer cascades.
 */

'use client';

import { memo, useMemo, useState, useCallback } from 'react';
import { cn } from '@/lib/utils';
import { Card, CardHeader, CardContent, CardTitle } from '@/components/ui';
import type { GEXSnapshot } from '@/types';

interface HedgingCascadeSimulatorProps {
  data?: GEXSnapshot | null;
  isLoading?: boolean;
}

interface CascadeStep {
  step: number;
  priceLevel: number;
  deltaChange: number; // shares/contracts dealers must trade
  marketImpact: number; // price impact of that hedging
  cumulativeMove: number; // total price displacement from original
  isBuying: boolean; // dealers buying or selling
  dampening: number; // 0-1, how much the cascade is dying
}

// Approximate market impact: for SPX, ~$1B in hedging moves price ~0.5-2 points
const LIQUIDITY_FACTOR = 2e9; // $2B of hedging per 1 point of impact (conservative)
const MAX_CASCADE_STEPS = 6;
const CASCADE_DAMPENING = 0.55; // Each step captures 55% of remaining impact

function formatDollars(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1e9) return `$${(value / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `$${(value / 1e6).toFixed(0)}M`;
  if (abs >= 1e3) return `$${(value / 1e3).toFixed(0)}K`;
  return `$${value.toFixed(0)}`;
}

function HedgingCascadeSimulatorComponent({ data, isLoading }: HedgingCascadeSimulatorProps) {
  const [hypotheticalMove, setHypotheticalMove] = useState(0); // points from current spot

  // Compute cascade for the given hypothetical move
  const cascade = useMemo((): CascadeStep[] => {
    if (!data?.gex_by_strike || !data.spot_price || hypotheticalMove === 0) return [];

    const spot = data.spot_price;
    const gexByStrike = data.gex_by_strike;
    const steps: CascadeStep[] = [];

    let currentPrice = spot;
    let remainingMove = hypotheticalMove;
    let cumulativeMove = 0;

    for (let step = 0; step < MAX_CASCADE_STEPS; step++) {
      if (Math.abs(remainingMove) < 0.5) break; // Stop when cascade dies

      const targetPrice = currentPrice + remainingMove;

      // Calculate net delta change across all strikes for this move
      // Gamma exposure at each strike: GEX ≈ OI × Γ × 100 × S²
      // Delta change when spot moves ΔS: ΔDelta ≈ (net_GEX / S²) × ΔS
      // Simplification: use net_gex directly as proxy for aggregate gamma
      let netDeltaChange = 0;

      for (const [strikeStr, gex] of Object.entries(gexByStrike)) {
        const strike = Number(strikeStr);
        const gexValue = Number(gex);
        if (!isFinite(gexValue)) continue;

        // Gamma's effect is strongest near the strike price
        const distance = Math.abs(currentPrice - strike);
        const proximity = Math.exp(-distance / 30); // Gaussian-like weighting

        // Delta change from this strike's gamma exposure
        // Positive GEX: dealers hedge AGAINST → dampening → negative feedback
        // Negative GEX: dealers hedge WITH → amplifying → positive feedback
        const deltaFromStrike = gexValue * proximity * remainingMove / (spot * spot);
        netDeltaChange += deltaFromStrike;
      }

      // Market impact of dealer hedging
      const marketImpact = (netDeltaChange / LIQUIDITY_FACTOR) * spot;
      const dampening = Math.pow(CASCADE_DAMPENING, step);

      cumulativeMove += remainingMove;

      steps.push({
        step: step + 1,
        priceLevel: targetPrice,
        deltaChange: netDeltaChange * 100, // Convert to dollar notional
        marketImpact: marketImpact * dampening,
        cumulativeMove,
        isBuying: netDeltaChange > 0,
        dampening,
      });

      // Next step: the market impact becomes the new "remaining move"
      remainingMove = marketImpact * dampening;
      currentPrice = targetPrice;
    }

    return steps;
  }, [data, hypotheticalMove]);

  // Total cascade amplification
  const totalAmplification = useMemo(() => {
    if (cascade.length === 0 || hypotheticalMove === 0) return 1;
    const totalImpact = cascade.reduce((sum, s) => sum + s.marketImpact, 0);
    return 1 + Math.abs(totalImpact / hypotheticalMove);
  }, [cascade, hypotheticalMove]);

  const isAmplifying = totalAmplification > 1.1;
  const isDampening = totalAmplification < 0.95;

  // Slider range: ±2% of spot
  const sliderRange = data?.spot_price ? Math.round(data.spot_price * 0.02) : 100;

  const handleSliderChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    setHypotheticalMove(Number(e.target.value));
  }, []);

  if (isLoading || !data) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Hedging Cascade Simulator</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-zinc-500">
            {isLoading ? 'Loading GEX data...' : 'Awaiting GEX data'}
          </p>
        </CardContent>
      </Card>
    );
  }

  const maxBarWidth = cascade.length > 0
    ? Math.max(...cascade.map((s) => Math.abs(s.marketImpact)), 1)
    : 1;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>
            Hedging Cascade Simulator
          </CardTitle>
          {hypotheticalMove !== 0 && (
            <div
              className={cn(
                'rounded-md px-2 py-0.5 text-xs font-bold',
                isAmplifying
                  ? 'bg-rose-900/50 text-rose-300'
                  : isDampening
                    ? 'bg-emerald-900/50 text-emerald-300'
                    : 'bg-zinc-800 text-zinc-400'
              )}
            >
              {isAmplifying
                ? `${totalAmplification.toFixed(2)}× Amplifying`
                : isDampening
                  ? `Dampened`
                  : `Neutral`}
            </div>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Slider */}
        <div>
          <div className="flex items-center justify-between text-xs text-zinc-400">
            <span>What if SPX moves...</span>
            <span
              className={cn(
                'font-bold tabular-nums text-sm',
                hypotheticalMove > 0
                  ? 'text-emerald-400'
                  : hypotheticalMove < 0
                    ? 'text-rose-400'
                    : 'text-zinc-500'
              )}
            >
              {hypotheticalMove > 0 ? '+' : ''}{hypotheticalMove} pts
            </span>
          </div>
          <input
            type="range"
            min={-sliderRange}
            max={sliderRange}
            step={1}
            value={hypotheticalMove}
            onChange={handleSliderChange}
            className="mt-2 w-full accent-violet-500"
          />
          <div className="flex justify-between text-[10px] text-zinc-600">
            <span>-{sliderRange}</span>
            <span>0</span>
            <span>+{sliderRange}</span>
          </div>
        </div>

        {/* Cascade Waterfall */}
        {cascade.length > 0 ? (
          <div className="space-y-1.5">
            <p className="text-[10px] font-medium uppercase tracking-wider text-zinc-500">
              Cascade Chain
            </p>

            {cascade.map((step, i) => {
              const barWidth = (Math.abs(step.marketImpact) / maxBarWidth) * 100;
              const isPositive = step.marketImpact > 0;

              return (
                <div key={i} className="relative">
                  {/* Step connector */}
                  {i > 0 && (
                    <div className="absolute -top-1 left-3 h-2 w-px bg-zinc-700" />
                  )}

                  <div className="flex items-center gap-2">
                    {/* Step number */}
                    <div
                      className={cn(
                        'flex h-6 w-6 items-center justify-center rounded-full text-[10px] font-bold',
                        i === 0
                          ? 'bg-violet-500/30 text-violet-300'
                          : 'bg-zinc-800 text-zinc-500'
                      )}
                      style={{ opacity: Math.max(0.3, step.dampening) }}
                    >
                      {step.step}
                    </div>

                    {/* Bar */}
                    <div className="flex-1">
                      <div className="relative h-5 overflow-hidden rounded bg-zinc-800/60">
                        <div
                          className={cn(
                            'h-full rounded transition-all duration-500',
                            isPositive
                              ? 'bg-gradient-to-r from-emerald-600/80 to-emerald-500/50'
                              : 'bg-gradient-to-r from-rose-600/80 to-rose-500/50'
                          )}
                          style={{
                            width: `${Math.max(2, barWidth)}%`,
                            opacity: Math.max(0.3, step.dampening),
                          }}
                        />
                        {/* Label inside bar */}
                        <div className="absolute inset-0 flex items-center justify-between px-2 text-[9px]">
                          <span className="font-medium text-zinc-300">
                            {step.isBuying ? 'Dealers BUY' : 'Dealers SELL'}
                          </span>
                          <span className="tabular-nums text-zinc-400">
                            {formatDollars(Math.abs(step.deltaChange))}
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* Impact value */}
                    <div
                      className={cn(
                        'w-14 text-right text-[10px] font-bold tabular-nums',
                        isPositive ? 'text-emerald-400' : 'text-rose-400'
                      )}
                      style={{ opacity: Math.max(0.4, step.dampening) }}
                    >
                      {isPositive ? '+' : ''}{step.marketImpact.toFixed(1)}
                    </div>
                  </div>
                </div>
              );
            })}

            {/* Total impact summary */}
            <div className="mt-3 rounded-lg border border-zinc-800 bg-zinc-900/50 px-3 py-2">
              <div className="flex items-center justify-between text-xs">
                <span className="text-zinc-400">Initial move</span>
                <span
                  className={cn(
                    'font-bold tabular-nums',
                    hypotheticalMove > 0 ? 'text-emerald-400' : 'text-rose-400'
                  )}
                >
                  {hypotheticalMove > 0 ? '+' : ''}{hypotheticalMove.toFixed(1)} pts
                </span>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-zinc-400">After cascade</span>
                <span
                  className={cn(
                    'font-bold tabular-nums',
                    hypotheticalMove > 0 ? 'text-emerald-400' : 'text-rose-400'
                  )}
                >
                  {hypotheticalMove > 0 ? '+' : ''}
                  {(hypotheticalMove * totalAmplification).toFixed(1)} pts
                </span>
              </div>
              <div className="mt-1 flex items-center justify-between border-t border-zinc-800 pt-1 text-xs">
                <span className="text-zinc-500">Amplification factor</span>
                <span
                  className={cn(
                    'font-bold',
                    isAmplifying ? 'text-rose-400' : 'text-emerald-400'
                  )}
                >
                  {totalAmplification.toFixed(2)}×
                </span>
              </div>
            </div>
          </div>
        ) : (
          <div className="flex h-32 items-center justify-center text-zinc-600">
            <div className="text-center">
              <p className="text-sm">Drag the slider to simulate a price move</p>
              <p className="mt-1 text-[10px] text-zinc-700">
                See how dealer hedging creates feedback loops
              </p>
            </div>
          </div>
        )}

        {/* Regime context */}
        <div className="text-[10px] text-zinc-600">
          {data.net_gex > 0
            ? 'Long Gamma: dealer hedging dampens moves (mean-reversion)'
            : 'Short Gamma: dealer hedging amplifies moves (trend-following)'}
        </div>
      </CardContent>
    </Card>
  );
}

export const HedgingCascadeSimulator = memo(HedgingCascadeSimulatorComponent);
