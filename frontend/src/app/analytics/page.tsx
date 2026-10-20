'use client';

import { useState } from 'react';
import { NavBar } from '@/components/ui/NavBar';
import { DataContext } from '@/components/ui/DataContext';
import { Card, CardHeader, CardContent, CardTitle, PageShell } from '@/components/ui';
import { ChartErrorBoundary, IVSurfaceChart, IVSkewChart, TechnicalOverlayChart } from '@/components/charts';
import { useIVSurface, useTechnicalIndicators, useRiskFreeRate } from '@/hooks/useAnalyticsData';
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
  const features = PROVIDER_FEATURES[selectedProvider as keyof typeof PROVIDER_FEATURES] ?? PROVIDER_FEATURES.yfinance;
  const providerName = availableProviders.find(p => p.name === selectedProvider)?.display_name ?? features.displayName;
  const { data: ivData, isLoading: ivLoading, error: ivError, refetch: refetchIV } = useIVSurface(symbol, features.supportsIvSurface);
  const { data: techData, isLoading: techLoading, error: techError, refetch: refetchTech } = useTechnicalIndicators(symbol, period, interval, 'ATR,RSI,BBANDS');
  const { data: rateData } = useRiskFreeRate();

  const visibleIV = ivError ? undefined : ivData;
  const visibleTech = techError ? undefined : techData;

  return <div className="min-h-screen"><NavBar /><PageShell variant="wide">
    <div className="page-heading"><div><h1>Analytics</h1><p>Implied volatility, skew and price context</p></div>
      <div className="page-tools"><div role="group" aria-label="Symbol" className="flex items-center gap-1"><span className="mr-2 text-sm text-zinc-400">Symbol</span>{SYMBOLS.map(s => <button type="button" key={s} className="control-button" aria-pressed={symbol === s} onClick={() => setSymbol(s)}>{s}</button>)}</div>{rateData && <span className="panel-caption">r {rateData.rate_pct.toFixed(2)}%{rateData.is_fallback ? ' · fallback' : ''}</span>}</div>
    </div>
    <p className="panel-caption mb-4">Selected provider: {providerName}. Each panel identifies the source actually used.</p>
    <section className="mb-5" aria-label="Implied volatility">
      {visibleIV && <div className="context-strip"><DataContext provenance={visibleIV.provenance} /></div>}
      {ivError ? <div role="alert" className="research-alert mb-4">IV data unavailable from {providerName}. No substitute spot or volatility is shown. <button type="button" className="control-button ml-2" onClick={() => void refetchIV()}>Retry IV data</button></div> : !features.supportsIvSurface ? <p className="research-alert mb-4">This provider does not support IV surfaces. Select another provider.</p> : null}
      <div className="grid grid-cols-2 gap-5">
        <Card><CardHeader><CardTitle>IV smile</CardTitle><span className="panel-caption">{visibleIV?.count ? `${visibleIV.count} contracts · ${symbol} spot ${visibleIV.spot_price.toFixed(2)}` : 'Call and put implied volatility'}</span></CardHeader><CardContent><ChartErrorBoundary chartName="IV smile"><IVSurfaceChart data={ivError ? [] : visibleIV?.surface ?? []} spotPrice={visibleIV?.spot_price ?? 0} isLoading={ivLoading} height={295} /></ChartErrorBoundary></CardContent></Card>
        <Card><CardHeader><CardTitle>IV skew</CardTitle><span className="panel-caption">Put IV − call IV · percentage points</span></CardHeader><CardContent><ChartErrorBoundary chartName="IV skew"><IVSkewChart data={ivError ? [] : visibleIV?.skew ?? []} isLoading={ivLoading} height={295} /></ChartErrorBoundary></CardContent></Card>
      </div>
    </section>
    <Card><CardHeader><CardTitle>Technical indicators</CardTitle><div className="flex items-center gap-5">
      <div role="group" aria-label="History period" className="flex items-center gap-1"><span className="panel-caption mr-2">Period</span>{PERIODS.map(p => <button type="button" key={p} className="control-button" aria-pressed={period === p} onClick={() => setPeriod(p)}>{p}</button>)}</div>
      <div role="group" aria-label="Bar interval" className="flex items-center gap-1"><span className="panel-caption mr-2">Interval</span>{INTERVALS.map(i => <button type="button" key={i} className="control-button" aria-pressed={interval === i} onClick={() => setInterval(i)}>{i}</button>)}</div>
    </div></CardHeader><CardContent>
      {visibleTech && <div className="mb-3"><DataContext provenance={visibleTech.provenance} /></div>}
      {techError ? <div role="alert" className="research-alert">Price history unavailable for {symbol}, {period} / {interval}. <button type="button" className="control-button ml-2" onClick={() => void refetchTech()}>Retry price history</button></div> : <ChartErrorBoundary chartName="Technical indicators"><TechnicalOverlayChart data={visibleTech?.data ?? []} indicators={visibleTech?.indicators ?? ['ATR', 'RSI', 'BBANDS']} isLoading={techLoading} height={340} /></ChartErrorBoundary>}
      {visibleTech && visibleTech.count < 20 && <p className="panel-caption mt-3">{visibleTech.count} bars available. Bollinger bands require 20 observations; choose a longer period or shorter interval.</p>}
    </CardContent></Card>
    <p className="panel-caption mt-5">IV: py_vollib · Indicators: pandas-ta · Risk-free rate: {rateData?.source ?? 'awaiting source'}. Captures and historical bars can have different sources and timestamps.</p>
  </PageShell></div>;
}
