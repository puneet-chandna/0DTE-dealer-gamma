'use client';

/**
 * 0DTE GEX Dashboard - Landing Page
 *
 * Shows connection status and basic GEX information.
 * Full dashboard will be implemented in Phase 4.
 */

import { useHealthCheck, useCurrentGEX, useCurrentRegime } from '@/hooks/useGEXData';
import { formatGEX, formatCurrency, getRegimeColor } from '@/lib/utils';

export default function Home() {
  const { data: health, isLoading: healthLoading, error: healthError } = useHealthCheck();
  const { data: gex, isLoading: gexLoading, error: gexError } = useCurrentGEX();
  const { data: regime, isLoading: regimeLoading } = useCurrentRegime();

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-50">
      {/* Header */}
      <header className="border-b border-zinc-800 px-6 py-4">
        <div className="mx-auto max-w-7xl flex items-center justify-between">
          <h1 className="text-xl font-semibold tracking-tight">
            0DTE GEX Monitor
          </h1>
          <div className="flex items-center gap-2">
            <span
              className={`h-2 w-2 rounded-full ${
                health?.status === 'healthy' ? 'bg-green-500' : 'bg-red-500'
              }`}
            />
            <span className="text-sm text-zinc-400">
              {healthLoading
                ? 'Connecting...'
                : health?.status === 'healthy'
                  ? 'API Connected'
                  : 'API Disconnected'}
            </span>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="mx-auto max-w-7xl px-6 py-12">
        {/* Status Banner */}
        {healthError && (
          <div className="mb-8 rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-red-400">
            <p className="text-sm">
              ⚠️ Backend API is not reachable. Start the backend server to see
              live data.
            </p>
          </div>
        )}

        {/* Quick Stats */}
        <div className="grid gap-6 md:grid-cols-3">
          {/* Net GEX Card */}
          <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-6">
            <h2 className="text-sm font-medium text-zinc-400">Net GEX</h2>
            {gexLoading ? (
              <div className="mt-2 h-8 w-32 animate-pulse rounded bg-zinc-800" />
            ) : gexError ? (
              <p className="mt-2 text-lg text-zinc-500">--</p>
            ) : (
              <p
                className={`mt-2 text-2xl font-bold ${
                  (gex?.net_gex ?? 0) < 0 ? 'text-red-400' : 'text-green-400'
                }`}
              >
                {gex ? formatGEX(gex.net_gex) : '--'}
              </p>
            )}
          </div>

          {/* Zero Gamma Level Card */}
          <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-6">
            <h2 className="text-sm font-medium text-zinc-400">
              Zero Gamma Level
            </h2>
            {gexLoading ? (
              <div className="mt-2 h-8 w-32 animate-pulse rounded bg-zinc-800" />
            ) : gexError ? (
              <p className="mt-2 text-lg text-zinc-500">--</p>
            ) : (
              <p className="mt-2 text-2xl font-bold text-zinc-50">
                {gex ? formatCurrency(gex.zero_gamma_level, 0) : '--'}
              </p>
            )}
          </div>

          {/* Market Regime Card */}
          <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-6">
            <h2 className="text-sm font-medium text-zinc-400">Market Regime</h2>
            {regimeLoading ? (
              <div className="mt-2 h-8 w-32 animate-pulse rounded bg-zinc-800" />
            ) : regime ? (
              <div className="mt-2">
                <p
                  className={`text-2xl font-bold capitalize ${getRegimeColor(
                    regime.regime
                  )}`}
                >
                  {regime.regime.replace('_', ' ')}
                </p>
                <p className="mt-1 text-sm text-zinc-500">
                  {regime.description}
                </p>
              </div>
            ) : (
              <p className="mt-2 text-lg text-zinc-500">--</p>
            )}
          </div>
        </div>

        {/* Spot Price */}
        <div className="mt-8 text-center">
          <p className="text-sm text-zinc-500">SPX Spot Price</p>
          <p className="text-4xl font-bold tracking-tight text-zinc-50">
            {gexLoading ? (
              <span className="inline-block h-10 w-40 animate-pulse rounded bg-zinc-800" />
            ) : gex ? (
              formatCurrency(gex.spot_price, 2)
            ) : (
              '--'
            )}
          </p>
        </div>

        {/* Info Section */}
        <div className="mt-16 text-center">
          <p className="text-sm text-zinc-500">
            Dashboard charts and detailed analytics coming in Phase 4.
          </p>
          <p className="mt-2 text-xs text-zinc-600">
            Data refreshes automatically every 30 seconds.
          </p>
        </div>
      </main>
    </div>
  );
}
