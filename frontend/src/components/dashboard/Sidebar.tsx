/**
 * Sidebar - Quick stats, settings, expirations
 */

'use client';

import { memo } from 'react';
import Link from 'next/link';
import { ChevronLeft, ChevronRight, Settings, Calendar, LineChart, FlaskConical, Waves } from 'lucide-react';
import { cn } from '@/lib/utils';
import { formatGEX, formatCurrency } from '@/lib/utils';
import { useUIStore } from '@/stores/uiStore';
import { MetricCard, Card, CardContent, Skeleton } from '@/components/ui';
import { RegimeIndicator } from '@/components/charts';
import { useRiskFreeRate } from '@/hooks/useAnalyticsData';
import type { GEXSnapshot, RegimeData } from '@/types';

interface SidebarProps {
  gexData?: GEXSnapshot | null;
  regimeData?: RegimeData | null;
  isLoading?: boolean;
}

function SidebarComponent({ gexData, regimeData, isLoading = false }: SidebarProps) {
  const { data: rateData } = useRiskFreeRate();
  const {
    isSidebarOpen,
    toggleSidebar,
    alertThreshold,
    setAlertThreshold,
    refreshInterval,
    setAutoRefresh,
    autoRefreshEnabled,
  } = useUIStore();

  // Calculate if we're in alert condition
  const isAlertActive = gexData
    ? Math.abs(gexData.net_gex / 1e9) >= alertThreshold
    : false;

  return (
    <aside
      className={cn(
        'relative flex flex-col border-r border-zinc-800 bg-zinc-950/50 transition-all duration-300',
        isSidebarOpen ? 'w-72' : 'w-14'
      )}
    >
      {/* Toggle button */}
      <button
        onClick={toggleSidebar}
        className="absolute -right-3 top-6 z-10 flex h-6 w-6 items-center justify-center rounded-full border border-zinc-700 bg-zinc-900 text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-zinc-300"
      >
        {isSidebarOpen ? (
          <ChevronLeft className="h-3.5 w-3.5" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5" />
        )}
      </button>

      {isSidebarOpen ? (
        <div className="flex-1 overflow-y-auto p-4">
          {/* Regime Indicator */}
          <div className="mb-6">
            {isLoading ? (
              <Skeleton className="h-20 w-full" />
            ) : regimeData ? (
              <RegimeIndicator
                regime={regimeData.regime}
                netGexBillions={regimeData.net_gex_billions}
                description={regimeData.description}
              />
            ) : (
              <div className="text-sm text-zinc-500">No regime data</div>
            )}
          </div>

          {/* Quick Stats */}
          <div className="space-y-3">
            <h3 className="text-xs font-medium uppercase tracking-wider text-zinc-500">
              Quick Stats
            </h3>

            <MetricCard
              label="Net GEX"
              value={gexData ? formatGEX(gexData.net_gex) : '--'}
              isLoading={isLoading}
              isNegative={gexData ? gexData.net_gex < 0 : false}
              isPositive={gexData ? gexData.net_gex > 0 : false}
            />

            <MetricCard
              label="Zero Gamma"
              value={gexData ? formatCurrency(gexData.zero_gamma_level, 0) : '--'}
              isLoading={isLoading}
            />

            <MetricCard
              label="Spot Price"
              value={gexData ? formatCurrency(gexData.spot_price, 2) : '--'}
              isLoading={isLoading}
            />

            <MetricCard
              label="Dominant Strike"
              value={gexData ? formatCurrency(gexData.dominant_strike, 0) : '--'}
              isLoading={isLoading}
            />

            <MetricCard
              label="Risk-Free Rate"
              value={rateData ? `${rateData.rate_pct.toFixed(2)}%` : '--'}
              isLoading={!rateData}
              isPositive={rateData ? !rateData.is_fallback : false}
            />
          </div>

          {/* Navigation Links */}
          <div className="mt-6 space-y-2">
            <h3 className="text-xs font-medium uppercase tracking-wider text-zinc-500">
              Pages
            </h3>
            <Link
              href="/analytics"
              className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-zinc-400 transition-colors hover:bg-zinc-800/60 hover:text-zinc-200"
            >
              <LineChart className="h-4 w-4" />
              Analytics
            </Link>
            <Link
              href="/dealer-flows"
              className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-zinc-400 transition-colors hover:bg-zinc-800/60 hover:text-zinc-200"
            >
              <Waves className="h-4 w-4" />
              Dealer Flows
            </Link>
            <Link
              href="/backtest"
              className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-zinc-400 transition-colors hover:bg-zinc-800/60 hover:text-zinc-200"
            >
              <FlaskConical className="h-4 w-4" />
              Backtest
            </Link>
          </div>

          {/* Settings */}
          <div className="mt-8 space-y-3">
            <h3 className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-zinc-500">
              <Settings className="h-3.5 w-3.5" />
              Settings
            </h3>

            <Card>
              <CardContent className="space-y-4">
                {/* Alert Threshold */}
                <div>
                  <label className="text-xs font-medium text-zinc-400">
                    Alert Threshold (B)
                  </label>
                  <div className="mt-1.5 flex items-center gap-2">
                    <input
                      type="range"
                      min="0.5"
                      max="3"
                      step="0.25"
                      value={alertThreshold}
                      onChange={(e) =>
                        setAlertThreshold(parseFloat(e.target.value))
                      }
                      className="flex-1 accent-violet-500"
                    />
                    <span className="w-12 text-right text-sm font-medium text-zinc-300">
                      {alertThreshold.toFixed(2)}B
                    </span>
                  </div>
                  {isAlertActive && (
                    <p className="mt-1 text-xs text-rose-400">
                      ⚠️ Alert threshold exceeded
                    </p>
                  )}
                </div>

                {/* Refresh Interval */}
                <div>
                  <label className="text-xs font-medium text-zinc-400">
                    Refresh Interval
                  </label>
                  <div className="mt-1.5 flex gap-1">
                    {[5, 10, 30, 60].map((seconds) => (
                      <button
                        key={seconds}
                        onClick={() => setAutoRefresh(autoRefreshEnabled, seconds)}
                        className={cn(
                          'flex-1 rounded px-2 py-1 text-xs font-medium transition-colors',
                          refreshInterval === seconds
                            ? 'bg-violet-500/20 text-violet-400 border border-violet-500/30'
                            : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'
                        )}
                      >
                        {seconds}s
                      </button>
                    ))}
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      ) : (
        /* Collapsed state - just icons */
        <div className="flex flex-col items-center gap-4 pt-12">
          <div
            className={cn(
              'h-3 w-3 rounded-full',
              regimeData?.regime === 'short_gamma'
                ? 'bg-rose-500'
                : regimeData?.regime === 'long_gamma'
                  ? 'bg-emerald-500'
                  : 'bg-amber-500'
            )}
            title={regimeData?.regime || 'No data'}
          />
          <Calendar className="h-4 w-4 text-zinc-500" />
          <Settings className="h-4 w-4 text-zinc-500" />
        </div>
      )}
    </aside>
  );
}

export const Sidebar = memo(SidebarComponent);
