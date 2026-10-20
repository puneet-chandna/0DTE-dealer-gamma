/**
 * HedgingCascadeSimulator — Interactive "What-If" Feedback Loop Visualizer.
 *
 * The user drags a slider to a hypothetical spot price. The simulator shows:
 * 1. Initial move → delta change across all strikes
 * 2. Dealer hedging → market impact
 * 3. Further price movement → more hedging → cascade
 *
 * An illustrative fixed-gamma scenario, not a forecast of dealer orders or price.
 */

'use client';

import { memo, useId, useMemo, useState, useCallback } from 'react';
import { cn } from '@/lib/utils';
import { Card, CardHeader, CardContent, CardTitle } from '@/components/ui';
import type { GEXSnapshot } from '@/types';

interface HedgingCascadeSimulatorProps {
  data?: GEXSnapshot | null;
  isLoading?: boolean;
}

interface CascadeStep {
  step: number;
  hedgeNotional: number; // signed dollars: buy positive, sell negative
  marketImpact: number; // price impact of that hedging
}

// shortcut: fixed, uncalibrated liquidity, replace only with validated impact data.
const LIQUIDITY_FACTOR = 2e9; // illustrative dollars of hedge notional per SPX point
const MAX_CASCADE_STEPS = 6;

function formatDollars(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1e9) return `$${(value / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `$${(value / 1e6).toFixed(0)}M`;
  if (abs >= 1e3) return `$${(value / 1e3).toFixed(0)}K`;
  return `$${value.toFixed(0)}`;
}

function HedgingCascadeSimulatorComponent({ data, isLoading }: HedgingCascadeSimulatorProps) {
  const [hypotheticalMove, setHypotheticalMove] = useState(0); // points from current spot
  const moveInputId = useId();

  const simulation = useMemo(() => {
    if (!data?.gex_by_strike || hypotheticalMove === 0) return null;

    const spot = data.spot_price;
    const values = Object.values(data.gex_by_strike);
    if (!Number.isFinite(spot) || spot <= 0 || !Number.isFinite(hypotheticalMove)
      || spot + hypotheticalMove <= 0 || values.length === 0
      || values.some((gex) => !Number.isFinite(gex))) return null;
    const netGex = values.reduce((sum, gex) => sum + gex, 0);
    if (!Number.isFinite(netGex)) return null;

    const steps: CascadeStep[] = [];
    let remainingMove = hypotheticalMove;
    let totalMove = hypotheticalMove;

    for (let step = 0; step < MAX_CASCADE_STEPS; step++) {
      // GEX = signed OI × gamma × 100 × S² × .01; hedge dollars = −GEX × ΔS / (.01 × S).
      const hedgeNotional = -(netGex / (0.01 * spot)) * remainingMove;
      const marketImpact = hedgeNotional / LIQUIDITY_FACTOR;
      totalMove += marketImpact;
      if (!Number.isFinite(hedgeNotional) || !Number.isFinite(totalMove)
        || !Number.isFinite(spot + totalMove) || spot + totalMove <= 0) return null;

      steps.push({ step: step + 1, hedgeNotional, marketImpact });
      if (marketImpact === 0) break;
      remainingMove = marketImpact;
    }

    return {
      steps,
      totalMove,
      amplification: totalMove / hypotheticalMove,
      unstable: Math.abs(netGex / (0.01 * spot) / LIQUIDITY_FACTOR) >= 1,
    };
  }, [data, hypotheticalMove]);

  const cascade = simulation?.steps ?? [];
  const totalAmplification = simulation?.amplification ?? 1;
  const isAmplifying = Math.abs(totalAmplification) > 1;
  const isDampening = Math.abs(totalAmplification) < 1;

  // Slider range: ±2% of spot
  const sliderRange = data && Number.isFinite(data.spot_price) && data.spot_price > 0
    ? Math.max(1, Math.round(data.spot_price * 0.02)) : 100;

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
          <p className="text-sm text-[var(--text-secondary)]">
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
          {hypotheticalMove !== 0 && simulation && (
            <div
              className={cn(
                'rounded-md px-2 py-0.5 text-sm font-bold',
                isAmplifying
                  ? 'bg-rose-900/50 text-rose-300'
                  : isDampening
                    ? 'bg-emerald-900/50 text-emerald-300'
                    : 'bg-zinc-800 text-[var(--text-secondary)]'
              )}
            >
              {simulation.unstable
                ? 'Unstable scenario'
                : isAmplifying
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
          <div className="flex items-center justify-between text-sm text-[var(--text-secondary)]">
            <label htmlFor={moveInputId}>Hypothetical SPX move (points)</label>
            <span
              className={cn(
                'font-bold tabular-nums text-sm',
                hypotheticalMove > 0
                  ? 'text-[var(--positive)]'
                  : hypotheticalMove < 0
                    ? 'text-[var(--negative)]'
                    : 'text-[var(--text-secondary)]'
              )}
            >
              {hypotheticalMove > 0 ? '+' : ''}{hypotheticalMove} pts
            </span>
          </div>
          <input
            id={moveInputId}
            type="range"
            min={-sliderRange}
            max={sliderRange}
            step={1}
            value={hypotheticalMove}
            aria-valuetext={`${hypotheticalMove > 0 ? '+' : ''}${hypotheticalMove} points`}
            onChange={handleSliderChange}
            className="mt-2 w-full accent-[var(--accent)]"
          />
          <div className="flex justify-between text-sm text-[var(--text-muted)]">
            <span>-{sliderRange}</span>
            <span>0</span>
            <span>+{sliderRange}</span>
          </div>
        </div>

        {/* Cascade Waterfall */}
        {simulation ? (
          <div className="space-y-1.5">
            <p className="text-sm font-medium uppercase tracking-wider text-[var(--text-secondary)]">
              Cascade chain (hedge $ / impact pts)
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
                        'flex h-7 w-7 items-center justify-center rounded-md text-sm font-medium',
                        i === 0
                          ? 'bg-violet-500/30 text-violet-300'
                          : 'bg-zinc-800 text-[var(--text-secondary)]'
                      )}
                    >
                      {step.step}
                    </div>

                    {/* Bar */}
                    <div className="flex-1">
                      <div className="flex items-center justify-between gap-3 text-sm">
                        <span className="font-medium text-[var(--text-primary)]">
                          {step.hedgeNotional === 0 ? 'No hedge adjustment' : step.hedgeNotional > 0 ? 'Dealers BUY' : 'Dealers SELL'}
                        </span>
                        <span className="tabular-nums text-[var(--text-secondary)]">{formatDollars(Math.abs(step.hedgeNotional))}</span>
                      </div>
                      <div aria-hidden="true" className="mt-1.5 h-1.5 overflow-hidden rounded bg-[var(--surface-raised)]">
                        <div
                          className={cn(
                            'h-full rounded',
                            isPositive
                              ? 'bg-[var(--positive)]'
                              : 'bg-[var(--negative)]'
                          )}
                          style={{
                            width: `${Math.max(2, barWidth)}%`,
                          }}
                        />
                      </div>
                    </div>

                    {/* Impact value */}
                    <div
                      className={cn(
                        'w-20 text-right text-sm font-medium tabular-nums',
                        isPositive ? 'text-[var(--positive)]' : 'text-[var(--negative)]'
                      )}
                    >
                      {isPositive ? '+' : ''}{step.marketImpact.toFixed(1)} pts
                    </div>
                  </div>
                </div>
              );
            })}

            {/* Total impact summary */}
            <div className="mt-3 rounded-lg border border-[var(--stroke)] bg-[var(--surface-base)] px-3 py-2">
              <div className="flex items-center justify-between text-sm">
                <span className="text-[var(--text-secondary)]">Initial move</span>
                <span
                  className={cn(
                    'font-bold tabular-nums',
                    hypotheticalMove > 0 ? 'text-[var(--positive)]' : 'text-[var(--negative)]'
                  )}
                >
                  {hypotheticalMove > 0 ? '+' : ''}{hypotheticalMove.toFixed(1)} pts
                </span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-[var(--text-secondary)]">After cascade</span>
                <span
                  className={cn(
                    'font-bold tabular-nums',
                    simulation.totalMove > 0 ? 'text-[var(--positive)]' : 'text-[var(--negative)]'
                  )}
                >
                  {simulation.totalMove > 0 ? '+' : ''}
                  {simulation.totalMove.toFixed(1)} pts
                </span>
              </div>
              <div className="mt-1 flex items-center justify-between border-t border-[var(--stroke)] pt-1 text-sm">
                <span className="text-[var(--text-secondary)]">Signed move ratio</span>
                <span
                  className={cn(
                    'font-bold',
                    isAmplifying ? 'text-[var(--negative)]' : 'text-[var(--positive)]'
                  )}
                >
                  {totalAmplification.toFixed(2)}×
                </span>
              </div>
            </div>
          </div>
        ) : (
          <div className="flex h-32 items-center justify-center text-[var(--text-muted)]">
            <div className="text-center">
              <p className="text-sm">
                {hypotheticalMove === 0 ? 'Move the slider or use arrow keys to simulate a price move' : 'Simulation unavailable for these GEX or price values'}
              </p>
              <p className="mt-1 text-sm text-[var(--text-muted)]">
                Illustrative feedback under fixed gamma and liquidity
              </p>
            </div>
          </div>
        )}

        <div className="text-sm text-[var(--text-secondary)]">
          Illustration only: fixed snapshot gamma, baseline call/put inventory signs,
          and an uncalibrated $2B hedge notional per SPX point. Capped at six rounds;
          no option repricing or liquidity forecast. An unstable scenario means
          feedback does not shrink under these assumptions.
        </div>
      </CardContent>
    </Card>
  );
}

export const HedgingCascadeSimulator = memo(HedgingCascadeSimulatorComponent);
