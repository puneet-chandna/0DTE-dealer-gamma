/**
 * Analytics Page — IV Surface, Skew, and Technical Indicators.
 *
 * Layout:
 * ┌─────────────────────────────────────────────────────────────┐
 * │  NavBar                                                      │
 * ├──────────────────────┬──────────────────────────────────────┤
 * │  IV Smile Chart      │  IV Skew Chart                       │
 * ├──────────────────────┴──────────────────────────────────────┤
 * │  Technical Indicators (Price + BBANDS + ATR + RSI)           │
 * └─────────────────────────────────────────────────────────────┘
 */

'use client';

import { useState } from 'react';
import { NavBar } from '@/components/ui/NavBar';
import { Card, CardHeader, CardContent, CardTitle, PageShell } from '@/components/ui';
import { ChartErrorBoundary, IVSurfaceChart, IVSkewChart, TechnicalOverlayChart } from '@/components/charts';
import { useIVSurface, useTechnicalIndicators, useRiskFreeRate } from '@/hooks/useAnalyticsData';
import { cn } from '@/lib/utils';
import { useUIStore } from '@/stores/uiStore';
import { PROVIDER_FEATURES } from '@/types';

const SYMBOLS = ['SPY', 'QQQ', 'IWM'] as const;
const PERIODS = ['5d', '1mo', '3mo', '6mo', '1y'] as const;
const INTERVALS = ['1h', '1d', '1wk'] as const;

export default function AnalyticsPage() {
  const [symbol, setSymbol] = useState<string>('SPY');
  const [period, setPeriod] = useState<string>('1mo');
  const [interval, setInterval] = useState<string>('1d');
  const { selectedProvider, availableProviders = [] } = useUIStore();
  const selectedProviderInfo = availableProviders.find(
    (provider) => provider.name === selectedProvider
  );
  const providerFeatures =
    PROVIDER_FEATURES[selectedProvider as keyof typeof PROVIDER_FEATURES] ??
    PROVIDER_FEATURES.yfinance;
  const providerDisplayName =
    selectedProviderInfo?.display_name ??
    providerFeatures.displayName ??
    selectedProvider;
  const technicalIndicatorsEnabled = providerFeatures.supportsTechnicalIndicators;

  const { data: ivData, isLoading: ivLoading, error: ivError } = useIVSurface(
    symbol,
    providerFeatures.supportsIvSurface
  );
  const { data: techData, isLoading: techLoading, error: techError } = useTechnicalIndicators(
    symbol,
    period,
    interval,
    'ATR,RSI,BBANDS',
    technicalIndicatorsEnabled
  );
  const { data: rateData } = useRiskFreeRate();

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-50">
      <NavBar />

      <PageShell variant="standard">
        {/* Page Header */}
        <div className="mb-8 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Analytics</h1>
            <p className="mt-1 text-sm text-zinc-400">
              IV surface, skew analysis, and technical overlays
            </p>
            <p className="mt-2 text-xs uppercase tracking-[0.18em] text-zinc-500">
              Provider: {providerDisplayName}
            </p>
          </div>

          {/* Symbol Selector */}
          <div className="flex flex-wrap items-center gap-2 sm:gap-3">
            <span className="text-xs text-zinc-500">Symbol</span>
            <div className="flex flex-wrap gap-1">
              {SYMBOLS.map((s) => (
                <button
                  key={s}
                  onClick={() => setSymbol(s)}
                  className={cn(
                    'rounded-lg px-3 py-1.5 text-xs font-medium transition-all',
                    symbol === s
                      ? 'bg-violet-500/15 text-violet-300 ring-1 ring-violet-500/25'
                      : 'bg-zinc-800/60 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200'
                  )}
                >
                  {s}
                </button>
              ))}
            </div>

            {/* Risk-free rate badge */}
            {rateData && (
              <div className={cn(
                'flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs sm:ml-2',
                rateData.is_fallback
                  ? 'bg-amber-500/10 text-amber-400 ring-1 ring-amber-500/20'
                  : 'bg-emerald-500/10 text-emerald-400 ring-1 ring-emerald-500/20'
              )}>
                <span className="font-mono">{rateData.rate_pct.toFixed(2)}%</span>
                <span className="text-zinc-500">r</span>
              </div>
            )}
          </div>
        </div>

        {/* IV Surface + Skew Row */}
            <div className="mb-6 grid gap-6 xl:grid-cols-2">
              {/* IV Smile */}
              <Card>
                <CardHeader>
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                    <CardTitle>IV Smile</CardTitle>
                    {ivData && (
                      <span className="text-xs text-zinc-500">
                        {ivData.count} strikes • SPX @ {ivData.spot_price?.toLocaleString()}
                      </span>
                    )}
                  </div>
                </CardHeader>
                <CardContent>
                  <ChartErrorBoundary chartName="IV Surface">
                    {ivError ? (
                      <div className="flex h-[300px] items-center justify-center rounded-lg border border-zinc-800 bg-zinc-900/50">
                        <p className="text-sm text-rose-400">Failed to load IV data</p>
                      </div>
                    ) : (
                      <IVSurfaceChart
                        data={ivData?.surface ?? []}
                        spotPrice={ivData?.spot_price ?? 0}
                        isLoading={ivLoading}
                        height={300}
                      />
                    )}
                  </ChartErrorBoundary>
                </CardContent>
              </Card>

              {/* IV Skew */}
              <Card>
                <CardHeader>
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                    <CardTitle>IV Skew</CardTitle>
                    <span className="text-xs text-zinc-500">Put IV − Call IV</span>
                  </div>
                </CardHeader>
                <CardContent>
                  <ChartErrorBoundary chartName="IV Skew">
                    {ivError ? (
                      <div className="flex h-[300px] items-center justify-center rounded-lg border border-zinc-800 bg-zinc-900/50">
                        <p className="text-sm text-rose-400">Failed to load skew data</p>
                      </div>
                    ) : (
                      <IVSkewChart
                        data={ivData?.skew ?? []}
                        isLoading={ivLoading}
                        height={300}
                      />
                    )}
                  </ChartErrorBoundary>
                </CardContent>
              </Card>
            </div>

            {/* Technical Indicators Section */}
            <Card>
              <CardHeader>
                <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                  <CardTitle>Technical Indicators</CardTitle>
                  <div className="flex flex-wrap items-center gap-3">
                    {/* Period selector */}
                    <div className="flex flex-wrap items-center gap-1">
                      <span className="mr-1 text-xs text-zinc-500">Period</span>
                      {PERIODS.map((p) => (
                        <button
                          key={p}
                          onClick={() => setPeriod(p)}
                          className={cn(
                            'rounded px-2 py-1 text-xs font-medium transition-all',
                            period === p
                              ? 'bg-violet-500/15 text-violet-300 ring-1 ring-violet-500/25'
                              : 'bg-zinc-800/60 text-zinc-400 hover:bg-zinc-800'
                          )}
                        >
                          {p}
                        </button>
                      ))}
                    </div>

                    {/* Interval selector */}
                    <div className="flex flex-wrap items-center gap-1">
                      <span className="mr-1 text-xs text-zinc-500">Int</span>
                      {INTERVALS.map((i) => (
                        <button
                          key={i}
                          onClick={() => setInterval(i)}
                          className={cn(
                            'rounded px-2 py-1 text-xs font-medium transition-all',
                            interval === i
                              ? 'bg-violet-500/15 text-violet-300 ring-1 ring-violet-500/25'
                              : 'bg-zinc-800/60 text-zinc-400 hover:bg-zinc-800'
                          )}
                        >
                          {i}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <ChartErrorBoundary chartName="Technical Indicators">
                  {!technicalIndicatorsEnabled ? (
                    <div className="flex h-[400px] items-center justify-center rounded-lg border border-zinc-800 bg-zinc-900/50">
                      <p className="text-sm text-amber-300">
                        {providerFeatures.technicalIndicatorsUnavailableReason ??
                          `Technical indicators are currently unavailable for ${providerDisplayName}.`}
                      </p>
                    </div>
                  ) : techError ? (
                    <div className="flex h-[400px] items-center justify-center rounded-lg border border-zinc-800 bg-zinc-900/50">
                      <p className="text-sm text-rose-400">Failed to load indicator data</p>
                    </div>
                  ) : (
                    <TechnicalOverlayChart
                      data={techData?.data ?? []}
                      indicators={techData?.indicators ?? ['ATR', 'RSI', 'BBANDS']}
                      isLoading={techLoading}
                      height={350}
                    />
                  )}
                </ChartErrorBoundary>
              </CardContent>
            </Card>

        {/* Footer */}
        <div className="mt-8 text-center">
          <p className="text-xs text-zinc-600">
            IV computed via py_vollib • Technical indicators via pandas-ta • Risk-free rate: {rateData?.source ?? 'loading...'}
          </p>
        </div>
      </PageShell>
    </div>
  );
}
