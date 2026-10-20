'use client';

import { useMemo } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useDashboardData, useIntradayTimeSeries } from '@/hooks/useDashboardData';
import { useGEXByStrikes, queryKeys } from '@/hooks/useGEXData';
import { getAppDataMode } from '@/lib/appMode';
import { formatCurrency, formatGEX, formatZeroGammaValue, hasZeroGammaCrossing } from '@/lib/utils';
import { useUIStore } from '@/stores/uiStore';
import { DashboardHeader, Sidebar } from '@/components/dashboard';
import { Card, CardHeader, CardContent, CardTitle, PageShell } from '@/components/ui';
import { SnapshotContext } from '@/components/ui/DataContext';
import { ChartErrorBoundary, GEXBarChart, TimeSeriesChart } from '@/components/charts';
import type { GEXChartDataPoint, TimeSeriesDataPoint } from '@/types';

export default function DashboardPage() {
  const queryClient = useQueryClient();
  const { demoModeEnabled, selectedProvider } = useUIStore();
  const mode = getAppDataMode(demoModeEnabled);
  // Hybrid data hook - prefers WebSocket, falls back to polling
  const {
    gexData,
    strikesData,
    isRealtime,
    connectionState,
    isLoading,
    isStale,
    lastUpdateTime,
    retryCount,
    reconnect,
    error,
  } = useDashboardData();

  // Intraday time series from WebSocket accumulation
  const { timeSeries: intradayData, dataPointCount } = useIntradayTimeSeries(gexData, lastUpdateTime);

  // Additional strikes data from REST (for full breakdown)
  const { data: strikesDataRest, isLoading: strikesLoading } = useGEXByStrikes();

  // Use whichever strikes data is available
  const effectiveStrikesData = strikesData ?? strikesDataRest;

  // Transform strikes data for bar chart
  const barChartData: GEXChartDataPoint[] = useMemo(() => {
    if (!effectiveStrikesData?.strikes || !effectiveStrikesData?.gex_values) return [];

    return effectiveStrikesData.strikes.map((strike: number, index: number) => ({
      strike,
      gex: effectiveStrikesData.gex_values[index],
      gexBillions: effectiveStrikesData.gex_values[index] / 1e9,
    }));
  }, [effectiveStrikesData]);

  // Transform intraday time series data for chart
  const timeSeriesData: TimeSeriesDataPoint[] = useMemo(() => {
    return intradayData.map((point) => ({
      timestamp: new Date(point.timestamp).toISOString(),
      netGex: point.netGex,
      netGexBillions: point.netGex / 1e9,
      spotPrice: point.spotPrice,
    }));
  }, [intradayData]);

  // Refresh handler - invalidate all queries and reconnect WebSocket
  const handleRefresh = () => {
    queryClient.invalidateQueries({
      queryKey: queryKeys.gex.current(mode, selectedProvider),
    });
    queryClient.invalidateQueries({
      queryKey: queryKeys.gex.regime(mode, selectedProvider),
    });
    queryClient.invalidateQueries({
      queryKey: queryKeys.gex.strikes(mode, selectedProvider),
    });
    // Always reconnect WebSocket to clear stale WS state and force fresh data
    reconnect();
  };

  return <div className="min-h-screen">
    <DashboardHeader isRealtime={isRealtime} connectionState={connectionState} retryCount={retryCount} isLoading={isLoading} onRefresh={handleRefresh} />
    <PageShell variant="wide">
      <div className="page-heading"><div><h1>Market structure</h1><p>Signed options exposure and captured intraday context</p></div><span className="panel-caption">SPX research · 0DTE</span></div>
      <div className="context-strip"><SnapshotContext snapshot={gexData} isStale={isStale} /></div>
      {error && <div role="alert" className="research-alert mb-4">{gexData ? 'Refresh unavailable; retaining the labelled capture.' : `Market snapshot unavailable: ${error}. Choose Demo to explore a labelled replay or synthetic scenario.`}</div>}
      <dl className="metric-strip">
        <div><dt>Spot reference</dt><dd>{gexData ? formatCurrency(gexData.spot_price, 2) : '—'}</dd></div>
        <div><dt>Net GEX · $ / 1% move</dt><dd className={gexData && gexData.net_gex < 0 ? 'text-rose-400' : 'text-emerald-400'}>{gexData ? formatGEX(gexData.net_gex) : '—'}</dd></div>
        <div><dt>Zero gamma</dt><dd>{formatZeroGammaValue(gexData)}</dd></div>
        <div><dt>Signed inventory proxy</dt><dd>{gexData ? gexData.net_gex > 0 ? 'Positive GEX' : gexData.net_gex < 0 ? 'Negative GEX' : 'Zero net GEX' : '—'}</dd></div>
      </dl>
      <div className="dashboard-workspace">
        <div className="plot-stack min-w-0">
          <Card><CardHeader><CardTitle>GEX by strike</CardTitle><span className="panel-caption">Hedge notional per 1% spot move · $B</span></CardHeader><CardContent>
            <ChartErrorBoundary chartName="GEX by strike"><GEXBarChart data={barChartData} spotPrice={effectiveStrikesData?.spot_price ?? gexData?.spot_price ?? 0} zeroGammaLevel={gexData && !hasZeroGammaCrossing(gexData) ? undefined : effectiveStrikesData?.zero_gamma_level ?? gexData?.zero_gamma_level} isLoading={isLoading || strikesLoading} height={350} /></ChartErrorBoundary>
          </CardContent></Card>
          <Card><CardHeader><CardTitle>Intraday net GEX</CardTitle><span className="panel-caption">{dataPointCount} points · Eastern time</span></CardHeader><CardContent>
            <ChartErrorBoundary chartName="Intraday net GEX">{timeSeriesData.length > 0 ? <TimeSeriesChart data={timeSeriesData} isLoading={false} height={240} /> : <div className="empty-chart"><p>{isLoading ? 'Loading persisted intraday history…' : 'No persisted intraday history for this source'}</p><p className="panel-caption">Saved captures appear first; subsequent captures are appended.</p></div>}</ChartErrorBoundary>
          </CardContent></Card>
        </div>
        <Sidebar gexData={gexData} isLoading={isLoading} />
      </div>
    </PageShell>
  </div>;
}
