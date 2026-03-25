/**
 * Dealer Flows Page — Charm/Vanna hidden flows + Hawkes momentum gauge.
 *
 * Layout:
 * ┌─────────────────────────────────────────────────────────────┐
 * │  NavBar                                                      │
 * ├─────────────────────────┬───────────────────────────────────┤
 * │  Hidden Dealer Flows    │  Order Flow Momentum               │
 * └─────────────────────────┴───────────────────────────────────┘
 */

'use client';

import { NavBar } from '@/components/ui/NavBar';
import { HiddenFlowsPanel } from '@/components/dashboard';
import { MomentumGauge } from '@/components/charts';
import { useDashboardData } from '@/hooks/useDashboardData';

export default function DealerFlowsPage() {
  const { gexData, isLoading } = useDashboardData();

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-50">
      <NavBar />

      <main className="mx-auto max-w-7xl px-6 py-8">
        {/* Page Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold tracking-tight">Dealer Flows</h1>
          <p className="mt-1 text-sm text-zinc-400">
            Hidden hedging pressure from Charm &amp; Vanna, plus Hawkes order flow momentum
          </p>
        </div>

        {/* Panels */}
        <div className="grid gap-6 lg:grid-cols-2">
          <HiddenFlowsPanel
            data={gexData?.advanced_analytics?.charm_vanna}
            isLoading={isLoading}
          />
          <MomentumGauge
            data={gexData?.advanced_analytics?.hawkes}
            isLoading={isLoading}
          />
        </div>

        {/* Footer */}
        <div className="mt-8 text-center">
          <p className="text-xs text-zinc-600">
            Charm flow = 30 min forward time decay • Vanna flow = 1% IV drop scenario • Hawkes process tracks order momentum
          </p>
        </div>
      </main>
    </div>
  );
}
