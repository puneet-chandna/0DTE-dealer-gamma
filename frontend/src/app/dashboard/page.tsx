/**
 * Dashboard Page - Full GEX monitoring dashboard with real-time WebSocket integration
 *
 * Layout:
 * ┌─────────────────────────────────────────────────────────────────┐
 * │ Header: Logo | Connection Status | Controls                     │
 * ├─────────────────────────────────────────────────────────────────┤
 * │ Stale Data Banner (conditional)                                 │
 * │ Regime Banner (conditional)                                     │
 * ├─────────────┬───────────────────────────────────────────────────┤
 * │ Sidebar     │ Main Content                                      │
 * │ Quick Stats │ ┌─────────────────────────────────────────────┐   │
 * │ • Net GEX   │ │ GEX by Strike Bar Chart                     │   │
 * │ • Zero Γ    │ └─────────────────────────────────────────────┘   │
 * │ Settings    │ ┌────────────────────┬────────────────────────┐   │
 * │ • Threshold │ │ Time Series Chart  │ Metrics Panel          │   │
 * │ • Refresh   │ └────────────────────┴────────────────────────┘   │
 * └─────────────┴───────────────────────────────────────────────────┘
 */

'use client';

import { useMemo } from 'react';
import { format } from 'date-fns';
import { useQueryClient } from '@tanstack/react-query';
import { useDashboardData, useIntradayTimeSeries } from '@/hooks/useDashboardData';
import { useGEXByStrikes, queryKeys } from '@/hooks/useGEXData';
import { DashboardHeader, Sidebar, MetricsPanel } from '@/components/dashboard';
import {
  AlertBanner,
  regimeDescriptions,
  Card,
  CardHeader,
  CardContent,
  CardTitle,
  StaleDataBanner,
} from '@/components/ui';
import { ChartErrorBoundary, GEXBarChart, TimeSeriesChart } from '@/components/charts';
import type { GEXChartDataPoint, TimeSeriesDataPoint } from '@/types';

export default function DashboardPage() {
  const queryClient = useQueryClient();

  // Hybrid data hook - prefers WebSocket, falls back to polling
  const {
    gexData,
    regimeData,
    strikesData,
    isRealtime,
    connectionState,
    isLoading,
    isStale,
    lastUpdateTime,
    retryCount,
    reconnect,
  } = useDashboardData();

  // Intraday time series from WebSocket accumulation
  const { timeSeries: intradayData, dataPointCount } = useIntradayTimeSeries();

  // Additional strikes data from REST (for full breakdown)
  const { data: strikesDataRest, isLoading: strikesLoading } = useGEXByStrikes();

  // Use whichever strikes data is available
  const effectiveStrikesData = strikesData ?? strikesDataRest;

  // Format last update time
  const lastUpdate = lastUpdateTime
    ? format(new Date(lastUpdateTime), 'h:mm:ss a')
    : undefined;

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

  // Refresh handler - invalidate all queries
  const handleRefresh = () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.gex.current });
    queryClient.invalidateQueries({ queryKey: queryKeys.gex.regime });
    queryClient.invalidateQueries({ queryKey: queryKeys.gex.strikes });
    // Also reconnect WebSocket if disconnected
    if (!isRealtime) {
      reconnect();
    }
  };

  // Show regime banner for short gamma (warning)
  const showRegimeBanner = regimeData?.regime === 'short_gamma';

  return (
    <div className="flex h-screen flex-col bg-zinc-950 text-zinc-50">
      {/* Header with connection status */}
      <DashboardHeader
        isConnected={!isLoading && !!gexData}
        isRealtime={isRealtime}
        connectionState={connectionState}
        retryCount={retryCount}
        isLoading={isLoading}
        lastUpdate={lastUpdate}
        onRefresh={handleRefresh}
      />

      {/* Stale Data Warning Banner */}
      {isStale && (
        <div className="px-6 pt-4">
          <StaleDataBanner
            lastUpdateTime={lastUpdateTime}
            staleThresholdMs={60000}
          />
        </div>
      )}

      {/* Regime Alert Banner */}
      {showRegimeBanner && regimeData && (
        <div className="px-6 pt-4">
          <AlertBanner
            regime={regimeData.regime}
            description={regimeData.description || regimeDescriptions[regimeData.regime]}
            netGexBillions={regimeData.net_gex_billions}
          />
        </div>
      )}

      {/* Main Layout */}
      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar */}
        <Sidebar
          gexData={gexData}
          regimeData={regimeData}
          isLoading={isLoading}
        />

        {/* Main Content */}
        <main className="flex-1 overflow-y-auto p-6">
          <div className="mx-auto max-w-7xl space-y-6">
            {/* GEX Bar Chart - Primary visualization */}
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle>GEX by Strike</CardTitle>
                  <div className="flex items-center gap-3">
                    {isRealtime && (
                      <span className="inline-flex items-center gap-1 rounded bg-emerald-900/50 px-2 py-0.5 text-xs text-emerald-300">
                        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
                        Live
                      </span>
                    )}
                    {gexData?.spot_price !== undefined && (
                      <span className="text-xs text-zinc-500">
                        SPX @ {gexData.spot_price.toLocaleString()}
                      </span>
                    )}
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <ChartErrorBoundary chartName="GEX Bar Chart">
                  <GEXBarChart
                    data={barChartData}
                    spotPrice={effectiveStrikesData?.spot_price ?? gexData?.spot_price ?? 0}
                    zeroGammaLevel={effectiveStrikesData?.zero_gamma_level ?? gexData?.zero_gamma_level}
                    isLoading={strikesLoading}
                    height={350}
                  />
                </ChartErrorBoundary>
              </CardContent>
            </Card>

            {/* Bottom Row: Time Series + Metrics */}
            <div className="grid gap-6 lg:grid-cols-3">
              {/* Time Series Chart */}
              <div className="lg:col-span-2">
                <Card>
                  <CardHeader>
                    <div className="flex items-center justify-between">
                      <CardTitle>Intraday Net GEX</CardTitle>
                      {dataPointCount > 0 && (
                        <span className="text-xs text-zinc-500">
                          {dataPointCount} data points
                        </span>
                      )}
                    </div>
                  </CardHeader>
                  <CardContent>
                    <ChartErrorBoundary chartName="Time Series Chart">
                      {timeSeriesData.length > 0 ? (
                        <TimeSeriesChart
                          data={timeSeriesData}
                          isLoading={false}
                          height={250}
                        />
                      ) : (
                        <div className="flex h-[250px] items-center justify-center rounded-lg border border-zinc-800 bg-zinc-900/50">
                          <div className="text-center">
                            <p className="text-sm text-zinc-500">
                              {isLoading
                                ? 'Accumulating real-time data...'
                                : 'Waiting for telemetry...'}
                            </p>
                            <p className="mt-1 text-xs text-zinc-600">
                              Intraday GEX timeline will build up as data arrives
                            </p>
                          </div>
                        </div>
                      )}
                    </ChartErrorBoundary>
                  </CardContent>
                </Card>
              </div>

              {/* Metrics Panel */}
              <div>
                <MetricsPanel data={gexData} isLoading={isLoading} />
              </div>
            </div>

            {/* Footer info */}
            <div className="text-center">
              <p className="text-xs text-zinc-600">
                {isRealtime
                  ? 'Real-time data via WebSocket • Updates every 5 seconds during market hours (9:30 AM - 4:00 PM ET)'
                  : 'Polling data via REST API • Updates every 30 seconds during market hours (9:30 AM - 4:00 PM ET)'}
              </p>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
