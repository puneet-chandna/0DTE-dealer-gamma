/**
 * Dealer Flows — Institutional-Grade Intelligence Terminal
 *
 * Production-grade financial analytics dashboard with:
 *  - Top summary bar (price, regime, bias, flip point)
 *  - Underline-style tab navigation
 *  - Clean card system with subtle borders (#1E293B)
 *  - Signal breakdown with structured icons
 *  - Trust signals (data source, timestamps, disclaimer)
 *  - 8px grid spacing system
 */

'use client';

import { useState, useMemo } from 'react';
import { NavBar } from '@/components/ui/NavBar';
import { PageShell } from '@/components/ui/PageShell';
import { HiddenFlowsPanel, GammaMagnetField, HedgingCascadeSimulator } from '@/components/dashboard';
import { MomentumGauge, GammaDecayClock } from '@/components/charts';
import { useDashboardData } from '@/hooks/useDashboardData';
import { cn } from '@/lib/utils';
import { useUIStore } from '@/stores/uiStore';
import { PROVIDER_FEATURES } from '@/types';
import type { GEXSnapshot, CharmVannaSnapshot, HawkesState } from '@/types';

// ============================================================================
// Constants
// ============================================================================

type TabId = 'magnetics' | 'cascade' | 'decay' | 'hidden';

const TABS: { id: TabId; label: string; question: string }[] = [
  { id: 'magnetics', label: 'Price Magnetics', question: 'Where is price being pulled?' },
  { id: 'cascade', label: 'Cascade Risk', question: 'What happens if price moves?' },
  { id: 'decay', label: 'Gamma Decay', question: 'How much time do I have?' },
  { id: 'hidden', label: 'Hidden Flows', question: 'What are dealers doing right now?' },
];

// ============================================================================
// Interpretation Engine
// ============================================================================

function formatB(value: number): string {
  return `$${(value / 1e9).toFixed(2)}B`;
}
function formatM(value: number): string {
  return `$${(Math.abs(value) / 1e6).toFixed(0)}M`;
}

function getMagneticsInterpretation(data: GEXSnapshot | null) {
  if (!data?.gex_by_strike) return null;

  const entries = Object.entries(data.gex_by_strike)
    .map(([s, g]) => ({ strike: Number(s), gex: Number(g) }))
    .filter(e => isFinite(e.gex) && Math.abs(e.gex) > 0);

  if (entries.length === 0) return null;

  const sorted = [...entries].sort((a, b) => Math.abs(b.gex) - Math.abs(a.gex));
  const attractors = entries.filter(e => e.gex > 0).sort((a, b) => b.gex - a.gex);
  const repellers = entries.filter(e => e.gex < 0).sort((a, b) => a.gex - b.gex);

  let weightedPull = 0, totalWeight = 0;
  for (const f of attractors) {
    const dist = Math.abs(f.strike - data.spot_price) + 5;
    const pull = f.gex / Math.pow(dist, 1.5);
    weightedPull += f.strike * Math.abs(pull);
    totalWeight += Math.abs(pull);
  }
  const pullTarget = totalWeight > 0 ? weightedPull / totalWeight : data.spot_price;
  const pullDirection = pullTarget - data.spot_price;
  const isLongGamma = data.net_gex > 0;

  let hero = '';
  if (Math.abs(pullDirection) > 10) {
    hero = `SPX is being pulled toward ${pullTarget.toFixed(0)} — ${Math.abs(pullDirection).toFixed(0)} points ${pullDirection > 0 ? 'above' : 'below'} current spot.`;
  } else {
    hero = `Price is relatively balanced near current levels. No strong directional pull detected.`;
  }

  const bullets: string[] = [];
  if (attractors.length > 0) {
    bullets.push(`${attractors.length} attractor strikes (long gamma) create mean-reversion. Strongest: ${attractors[0].strike.toFixed(0)} with ${formatB(attractors[0].gex)} GEX.`);
  }
  if (repellers.length > 0) {
    bullets.push(`${repellers.length} repeller strikes (short gamma) amplify moves away. Strongest: ${repellers[0].strike.toFixed(0)} with ${formatB(repellers[0].gex)} GEX.`);
  }
  bullets.push(`Dominant strike: ${data.dominant_strike.toFixed(0)} — highest absolute GEX concentration.`);
  if (data.zero_gamma_level > 0) {
    const zglRelative = data.zero_gamma_level - data.spot_price;
    bullets.push(`Zero Gamma Level: ${data.zero_gamma_level.toFixed(0)} — ${Math.abs(zglRelative).toFixed(0)} pts ${zglRelative > 0 ? 'above' : 'below'} spot. Crossing this flips the regime.`);
  }

  let takeaway = '';
  if (isLongGamma && Math.abs(pullDirection) > 10) {
    takeaway = `Favor mean-reversion trades near ${pullTarget.toFixed(0)}. Long gamma dealers will dampen breakouts. Sell spikes, buy dips within the attractor zone.`;
  } else if (!isLongGamma) {
    takeaway = `Short gamma regime — price moves will be amplified. If spot pushes past repeller zones, expect acceleration. Trade with momentum, not against it.`;
  } else {
    takeaway = `Balanced positioning. No strong directional bias from dealer hedging. Focus on other signals for direction.`;
  }

  const keyLevels = sorted.slice(0, 4).map(e => ({
    price: e.strike.toFixed(0),
    label: e.gex > 0 ? 'Support' : 'Resistance',
    value: formatB(e.gex),
    type: (e.gex > 0 ? 'support' : 'resistance') as 'support' | 'resistance',
  }));

  return { hero, bullets, takeaway, keyLevels };
}

function getCascadeInterpretation(data: GEXSnapshot | null) {
  if (!data) return null;

  const isLongGamma = data.net_gex > 0;
  const netGexB = data.net_gex / 1e9;

  let hero = '';
  if (isLongGamma) {
    hero = `Dealers are long gamma (${netGexB.toFixed(2)}B). Price moves will be dampened by dealer hedging. Low cascade risk.`;
  } else {
    hero = `Dealers are short gamma (${netGexB.toFixed(2)}B). Price moves will be amplified by dealer hedging. Elevated cascade risk.`;
  }

  const bullets: string[] = [];
  bullets.push(isLongGamma
    ? `Long gamma dealers sell into rallies and buy dips — natural mean-reversion. Move amplification factor is typically < 1.0x.`
    : `Short gamma dealers buy into rallies and sell into dips — positive feedback. Move amplification can reach 1.5–3.0x during volatile sessions.`
  );
  bullets.push(`Net GEX: ${formatB(data.net_gex)} — ${Math.abs(netGexB) > 2 ? 'significant' : 'moderate'} positioning.`);
  bullets.push(`Use the slider to simulate a price shock and see the chain reaction step by step.`);
  bullets.push(isLongGamma
    ? `In long gamma, large moves are unlikely to sustain. Fades tend to work.`
    : `In short gamma, a 1% move can trigger $500M+ of directional hedging, creating a self-reinforcing loop.`
  );

  let takeaway = '';
  if (isLongGamma) {
    takeaway = `Low risk of flash crash or squeeze. Dealer hedging provides a natural buffer. Option sellers benefit from this regime.`;
  } else {
    takeaway = `Elevated cascade risk. Tight stops are critical. A catalyst (economic data, large flow) can trigger cascading hedging. Consider protective long gamma positions.`;
  }

  return { hero, bullets, takeaway };
}

function getDecayInterpretation(data: GEXSnapshot | null) {
  if (!data) return null;

  const now = new Date();
  const etString = now.toLocaleString('en-US', { timeZone: 'America/New_York' });
  const etDate = new Date(etString);
  const closeMinutes = 16 * 60;
  const currentMinutes = etDate.getHours() * 60 + etDate.getMinutes();
  const minutesLeft = Math.max(0, closeMinutes - currentMinutes);
  const openMinutes = 9 * 60 + 30;
  const marketOpen = currentMinutes >= openMinutes && currentMinutes < closeMinutes;

  const inDanger = minutesLeft <= 90 && minutesLeft > 0;
  const inCritical = minutesLeft <= 30 && minutesLeft > 0;
  const intensity = minutesLeft > 0 ? 1 / Math.sqrt(Math.max(minutesLeft / 390, 0.001)) : 0;

  let hero = '';
  if (!marketOpen) {
    hero = `Market is closed. 0DTE options have expired. Gamma exposure has reset to zero.`;
  } else if (inCritical) {
    hero = `CRITICAL — Only ${minutesLeft} minutes until close. Gamma is at ${intensity.toFixed(1)}x intensity. Maximum volatility risk.`;
  } else if (inDanger) {
    hero = `DANGER ZONE — ${minutesLeft} minutes until close. Gamma intensity is rising sharply. 0DTE options are entering the high-risk decay phase.`;
  } else if (minutesLeft <= 180) {
    hero = `Gamma intensity is elevated at ${intensity.toFixed(2)}x. The decay curve is steepening. ${minutesLeft} minutes to close.`;
  } else {
    hero = `${minutesLeft} minutes to close. Gamma intensity is stable at ${intensity.toFixed(2)}x. The curve steepens significantly after 2:30 PM ET.`;
  }

  const bullets: string[] = [];
  bullets.push(`Gamma is proportional to 1/sqrt(T) — for ATM 0DTE options, gamma increases exponentially as expiry approaches.`);
  if (marketOpen) {
    bullets.push(`Current intensity: ${intensity.toFixed(2)}x baseline. ${inDanger ? 'Abnormally high.' : 'Normal range.'}`);
    bullets.push(`Time remaining: ${minutesLeft} minutes until 4:00 PM ET close.`);
    if (inDanger) {
      bullets.push(`Pin risk: options with large OI near spot will create powerful pinning forces.`);
    }
    if (minutesLeft > 90) {
      bullets.push(`Danger zone begins at 2:30 PM ET (90 min). Critical zone begins at 3:30 PM ET (30 min).`);
    }
  } else {
    bullets.push(`All 0DTE options have expired. Gamma exposure resets tomorrow at market open.`);
  }

  let takeaway = '';
  if (!marketOpen) {
    takeaway = `No 0DTE gamma risk. Plan tomorrow's positioning based on expected OI distribution at open.`;
  } else if (inCritical) {
    takeaway = `Extreme caution. Reduce position sizes. Pin risk creates whipsaw reversals. Use limit orders only. Exit speculative positions.`;
  } else if (inDanger) {
    takeaway = `Tighten stops. Gamma amplification means moves can accelerate suddenly. Consider closing 0DTE short options.`;
  } else {
    takeaway = `Standard gamma environment. Plan exits before the danger zone if holding short gamma positions.`;
  }

  return { hero, bullets, takeaway, inDanger, inCritical, marketOpen };
}

function getHiddenFlowsInterpretation(
  charm_vanna: CharmVannaSnapshot | null | undefined,
  hawkes: HawkesState | null | undefined,
) {
  const hasCharmVanna = charm_vanna && (charm_vanna.charm_flow !== 0 || charm_vanna.vanna_flow !== 0);
  const hasHawkes = hawkes !== null && hawkes !== undefined;

  if (!hasCharmVanna && !hasHawkes) return null;

  let hero = '';
  const bullets: string[] = [];
  let takeaway = '';

  if (hasCharmVanna) {
    const netFlow = charm_vanna!.net_hidden_flow;
    const isPositive = netFlow >= 0;
    const charmDominant = Math.abs(charm_vanna!.charm_flow) > Math.abs(charm_vanna!.vanna_flow);

    hero = `Dealers have ${formatM(netFlow)} in net hidden flow — they are ${isPositive ? 'buying' : 'selling'} futures to stay delta-neutral. `;
    hero += charmDominant ? `Time decay (Charm) is the primary driver.` : `Volatility sensitivity (Vanna) is the primary driver.`;

    bullets.push(`Charm flow: ${formatM(charm_vanna!.charm_flow)} — hedging pressure from time decay in the next 30 minutes.`);
    bullets.push(`Vanna flow: ${formatM(charm_vanna!.vanna_flow)} — hedging pressure if implied volatility drops 1%.`);
    bullets.push(`Net hidden flow: ${formatM(netFlow)} — ${isPositive ? 'upward' : 'downward'} pressure on price.`);
  }

  if (hasHawkes) {
    const squeeze = Math.round(hawkes!.squeeze_probability * 100);
    const intensityThreshold = 0.2;
    const callDominant = hawkes!.call_intensity > hawkes!.put_intensity;
    const putDominant = hawkes!.put_intensity > hawkes!.call_intensity;
    const hasBalancedFlow = !callDominant && !putDominant;
    const isBalanced =
      hasBalancedFlow &&
      hawkes!.call_intensity < intensityThreshold &&
      hawkes!.put_intensity < intensityThreshold;
    const isBalancedButElevated = hasBalancedFlow && !isBalanced;

    if (!hero) {
      hero = isBalanced
        ? `Order flow momentum is balanced. Hawkes intensities are quiet right now, so there is no active call or put dominance.`
        : isBalancedButElevated
          ? `Order flow momentum is balanced, but Hawkes intensities are elevated on both sides. Squeeze probability: ${squeeze}%.`
        : `Order flow momentum is ${callDominant ? 'call-dominant' : 'put-dominant'}. Squeeze probability: ${squeeze}%.`;
    }

    bullets.push(`Call intensity: ${hawkes!.call_intensity.toFixed(2)} — ${hasBalancedFlow ? 'balanced with puts' : callDominant ? 'dominant' : 'subordinate'} side.`);
    bullets.push(`Put intensity: ${hawkes!.put_intensity.toFixed(2)} — ${hasBalancedFlow ? 'balanced with calls' : putDominant ? 'dominant' : 'subordinate'} side.`);
    bullets.push(`Squeeze probability: ${squeeze}% — ${squeeze > 60 ? 'high — squeeze conditions detected' : squeeze > 40 ? 'moderate — watch for buildup' : isBalanced ? 'low — no recent flow imbalance' : isBalancedButElevated ? 'low — balanced flow is elevated on both sides' : 'low — normal flow'}.`);
  }

  if (hasCharmVanna) {
    const isPositive = charm_vanna!.net_hidden_flow >= 0;
    takeaway = isPositive
      ? `Structural buying pressure from dealer hedging creates a supportive floor. Dips may be shallow.`
      : `Structural selling pressure from dealer hedging creates a headwind for rallies.`;
  } else {
    takeaway = `Monitor Hawkes intensities for flow direction. ${hawkes!.squeeze_probability > 0.5 ? 'Elevated squeeze probability suggests potential for rapid reversal.' : 'Normal flow conditions.'}`;
  }

  return { hero, bullets, takeaway };
}

// ============================================================================
// Summary Bar Helpers
// ============================================================================

function getRegimeLabel(netGex: number): { text: string; color: string } {
  if (netGex > 0) return { text: 'Long Gamma', color: 'text-emerald-400' };
  return { text: 'Short Gamma', color: 'text-rose-400' };
}

function getBias(data: GEXSnapshot): { text: string; color: string } {
  const isLong = data.net_gex > 0;
  if (isLong) return { text: 'Neutral / Dampened', color: 'text-zinc-300' };
  // Short gamma — check dominant flow direction
  if (data.spot_price > data.zero_gamma_level) return { text: 'Bearish Pressure', color: 'text-rose-400' };
  return { text: 'Bullish Pressure', color: 'text-emerald-400' };
}

// ============================================================================
// Page Component
// ============================================================================

export default function DealerFlowsPage() {
  const { gexData, isLoading } = useDashboardData();
  const { selectedProvider, availableProviders = [] } = useUIStore();
  const [activeTab, setActiveTab] = useState<TabId>('magnetics');
  const lastUpdated = gexData?.timestamp ? new Date(gexData.timestamp) : null;
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

  // Interpretations
  const magneticsInterp = useMemo(() => getMagneticsInterpretation(gexData), [gexData]);
  const cascadeInterp = useMemo(() => getCascadeInterpretation(gexData), [gexData]);
  const decayInterp = useMemo(() => getDecayInterpretation(gexData), [gexData]);
  const hiddenInterp = useMemo(
    () => getHiddenFlowsInterpretation(
      gexData?.advanced_analytics?.charm_vanna,
      gexData?.advanced_analytics?.hawkes,
    ),
    [gexData]
  );

  const activeTabData = TABS.find(t => t.id === activeTab)!;
  const regime = gexData ? getRegimeLabel(gexData.net_gex) : null;
  const bias = gexData ? getBias(gexData) : null;

  return (
    <div className="min-h-screen bg-[#0a0a0f] text-zinc-50">
      <NavBar />

      <PageShell variant="wide" className="pb-16 pt-6">
        {/* ──────────── Page Header ──────────── */}
        <div className="mb-6 flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-zinc-100">
              Dealer Flows
            </h1>
            <p className="mt-0.5 text-xs text-zinc-500">
              Institutional dealer positioning & hedging intelligence
            </p>
          </div>
          {/* Trust signals */}
          <div className="flex flex-wrap items-center gap-3 text-[11px] text-zinc-600">
            <span>Source: {providerDisplayName}</span>
            {lastUpdated && (
              <span>
                Updated {lastUpdated.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
              </span>
            )}
            <div className={cn(
              'h-1.5 w-1.5 rounded-full',
              isLoading ? 'bg-amber-500 animate-pulse' : gexData ? 'bg-emerald-500' : 'bg-zinc-600'
            )} />
          </div>
        </div>

        {/* ──────────── Summary Bar ──────────── */}
        <div className="mb-8 grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-[#1e293b] bg-[#1e293b] lg:grid-cols-4">
          {/* Price */}
          <div className="bg-[#0f1117] px-4 py-3 sm:px-5 sm:py-4">
            <p className="text-[10px] font-medium uppercase tracking-widest text-zinc-600">
              SPX Spot
            </p>
            <p className="mt-1 text-lg font-semibold tabular-nums text-zinc-100">
              {gexData ? gexData.spot_price.toFixed(2) : '—'}
            </p>
          </div>
          {/* Regime */}
          <div className="bg-[#0f1117] px-4 py-3 sm:px-5 sm:py-4">
            <p className="text-[10px] font-medium uppercase tracking-widest text-zinc-600">
              Regime
            </p>
            <p className={cn('mt-1 text-lg font-semibold', regime?.color ?? 'text-zinc-500')}>
              {regime?.text ?? '—'}
            </p>
          </div>
          {/* Bias */}
          <div className="bg-[#0f1117] px-4 py-3 sm:px-5 sm:py-4">
            <p className="text-[10px] font-medium uppercase tracking-widest text-zinc-600">
              Dealer Bias
            </p>
            <p className={cn('mt-1 text-lg font-semibold', bias?.color ?? 'text-zinc-500')}>
              {bias?.text ?? '—'}
            </p>
          </div>
          {/* Flip Point */}
          <div className="bg-[#0f1117] px-4 py-3 sm:px-5 sm:py-4">
            <p className="text-[10px] font-medium uppercase tracking-widest text-zinc-600">
              Gamma Flip
            </p>
            <p className="mt-1 text-lg font-semibold tabular-nums text-violet-400">
              {gexData && gexData.zero_gamma_level > 0 ? gexData.zero_gamma_level.toFixed(0) : '—'}
            </p>
          </div>
        </div>

        {/* ──────────── Tab Navigation ──────────── */}
        <div className="mb-8 overflow-x-auto border-b border-[#1e293b]">
          <div className="flex min-w-max gap-1">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={cn(
                  'relative flex-none rounded-t-lg px-4 py-3 text-[13px] font-medium tracking-tight transition-colors duration-150 sm:px-5',
                  activeTab === tab.id
                    ? 'text-zinc-100'
                    : 'text-zinc-500 hover:text-zinc-300'
                )}
              >
                {tab.label}
                {/* Active underline */}
                {activeTab === tab.id && (
                  <div className="absolute bottom-0 left-0 right-0 h-[2px] bg-violet-500" />
                )}
              </button>
            ))}
          </div>
        </div>

        {/* ──────────── Tab Question ──────────── */}
        <p className="mb-6 text-sm text-zinc-400">
          {activeTabData.question}
        </p>

        {/* ──────────── Tab Content ──────────── */}
        {activeTab === 'magnetics' && (
          <TabLayout
            hero={magneticsInterp?.hero}
            bullets={magneticsInterp?.bullets}
            takeaway={magneticsInterp?.takeaway}
            keyLevels={magneticsInterp?.keyLevels}
            isLoading={isLoading}
          >
            <GammaMagnetField data={gexData} isLoading={isLoading} />
          </TabLayout>
        )}

        {activeTab === 'cascade' && (
          <TabLayout
            hero={cascadeInterp?.hero}
            bullets={cascadeInterp?.bullets}
            takeaway={cascadeInterp?.takeaway}
            isLoading={isLoading}
          >
            <HedgingCascadeSimulator data={gexData} isLoading={isLoading} />
          </TabLayout>
        )}

        {activeTab === 'decay' && (
          <TabLayout
            hero={decayInterp?.hero}
            bullets={decayInterp?.bullets}
            takeaway={decayInterp?.takeaway}
            alertLevel={decayInterp?.inCritical ? 'critical' : decayInterp?.inDanger ? 'danger' : undefined}
            isLoading={isLoading}
          >
            <GammaDecayClock data={gexData} isLoading={isLoading} />
          </TabLayout>
        )}

        {activeTab === 'hidden' && (
          <TabLayout
            hero={hiddenInterp?.hero}
            bullets={hiddenInterp?.bullets}
            takeaway={hiddenInterp?.takeaway}
            isLoading={isLoading}
          >
            <div className="grid gap-6 xl:grid-cols-2">
              <HiddenFlowsPanel
                data={gexData?.advanced_analytics?.charm_vanna}
                isLoading={isLoading}
              />
              <MomentumGauge
                data={gexData?.advanced_analytics?.hawkes}
                isLoading={isLoading}
              />
            </div>
          </TabLayout>
        )}

        {/* ──────────── Disclaimer ──────────── */}
        <div className="mt-12 border-t border-[#1e293b] pt-4">
          <p className="text-[10px] leading-relaxed text-zinc-700">
            This analysis is derived from publicly available options data and mathematical models of dealer gamma exposure.
            It does not constitute financial advice. Dealer positioning is one structural factor among many.
            Past gamma regimes do not guarantee future price behavior.
          </p>
        </div>
      </PageShell>
    </div>
  );
}

// ============================================================================
// TabLayout — Institutional Card System
// ============================================================================

interface KeyLevel {
  price: string;
  label: string;
  value: string;
  type: 'support' | 'resistance';
}

interface TabLayoutProps {
  hero?: string | null;
  bullets?: string[] | null;
  takeaway?: string | null;
  keyLevels?: KeyLevel[] | null;
  alertLevel?: 'danger' | 'critical';
  isLoading: boolean;
  children: React.ReactNode;
}

function TabLayout({
  hero,
  bullets,
  takeaway,
  keyLevels,
  alertLevel,
  isLoading,
  children,
}: TabLayoutProps) {
  return (
    <div className="space-y-5 sm:space-y-6">
      {/* ── Hero Insight ── */}
      {hero && (
        <div
          className={cn(
            'rounded-md border-l-2 px-4 py-3 sm:px-5',
            alertLevel === 'critical'
              ? 'border-l-rose-500 bg-rose-950/20'
              : alertLevel === 'danger'
                ? 'border-l-amber-500 bg-amber-950/10'
                : 'border-l-[#1e293b] bg-[#0f1117]'
          )}
        >
          <p
            className={cn(
              'text-[13px] leading-relaxed',
              alertLevel === 'critical'
                ? 'text-rose-200'
                : alertLevel === 'danger'
                  ? 'text-amber-200'
                  : 'text-zinc-300'
            )}
          >
            {hero}
          </p>
        </div>
      )}

      {/* ── Main Grid: Visualization + Intelligence Panel ── */}
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.65fr)_minmax(360px,1fr)]">
        {/* Visualization — 3 cols */}
        <div>
          {children}
        </div>

        {/* Intelligence Panel — 2 cols */}
        <div className="space-y-4">
          {/* Signal Breakdown */}
          {bullets && bullets.length > 0 && (
            <div className="overflow-hidden rounded-md border border-[#1e293b] bg-[#0f1117]">
              <div className="flex items-center gap-2 border-b border-[#1e293b] px-4 py-2.5">
                <div className="h-1 w-1 rounded-full bg-violet-500" />
                <h3 className="text-[10px] font-semibold uppercase tracking-widest text-zinc-500">
                  Signal Breakdown
                </h3>
              </div>
              <div className="divide-y divide-[#1e293b]/60">
                {bullets.map((bullet, i) => (
                  <div
                    key={i}
                    className="flex gap-3 px-4 py-3 transition-colors duration-100 hover:bg-white/[0.02]"
                  >
                    <span className="flex h-[18px] w-[18px] flex-none items-center justify-center rounded-sm bg-zinc-800 text-[9px] font-bold tabular-nums text-zinc-500">
                      {i + 1}
                    </span>
                    <p className="text-[12px] leading-[1.6] text-zinc-400">
                      {bullet}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Critical Strikes */}
          {keyLevels && keyLevels.length > 0 && (
            <div className="overflow-hidden rounded-md border border-[#1e293b] bg-[#0f1117]">
              <div className="flex items-center gap-2 border-b border-[#1e293b] px-4 py-2.5">
                <div className="h-1 w-1 rounded-full bg-amber-500" />
                <h3 className="text-[10px] font-semibold uppercase tracking-widest text-zinc-500">
                  Critical Strikes
                </h3>
              </div>
              <div className="divide-y divide-[#1e293b]/60">
                {keyLevels.map((level, i) => (
                  <div
                    key={i}
                    className="flex flex-col gap-2 px-4 py-3 transition-colors duration-100 hover:bg-white/[0.02] sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div className="flex items-center gap-2">
                      <div className={cn(
                        'h-1.5 w-1.5 rounded-full',
                        level.type === 'support' ? 'bg-emerald-500' : 'bg-rose-500'
                      )} />
                      <span className={cn(
                        'text-[13px] font-semibold tabular-nums',
                        level.type === 'support' ? 'text-emerald-400' : 'text-rose-400'
                      )}>
                        {level.price}
                      </span>
                      <span className={cn(
                        'rounded px-1.5 py-px text-[9px] font-medium uppercase tracking-wide',
                        level.type === 'support'
                          ? 'bg-emerald-500/10 text-emerald-500'
                          : 'bg-rose-500/10 text-rose-500'
                      )}>
                        {level.label}
                      </span>
                    </div>
                    <span className="text-[11px] tabular-nums text-zinc-500 sm:text-right">{level.value}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Loading skeleton */}
          {isLoading && !bullets && (
            <div className="rounded-md border border-[#1e293b] bg-[#0f1117] px-4 py-4">
              <div className="animate-pulse space-y-3">
                <div className="h-2 w-20 rounded bg-zinc-800" />
                <div className="h-2 w-full rounded bg-zinc-800" />
                <div className="h-2 w-4/5 rounded bg-zinc-800" />
                <div className="h-2 w-3/5 rounded bg-zinc-800" />
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── Desk Note ── */}
      {takeaway && (
        <div
          className={cn(
            'rounded-md border px-4 py-3 sm:px-5',
            alertLevel === 'critical'
              ? 'border-rose-900/40 bg-rose-950/10'
              : alertLevel === 'danger'
                ? 'border-amber-900/30 bg-amber-950/10'
                : 'border-[#1e293b] bg-[#0f1117]'
          )}
        >
          <div className="flex items-start gap-3">
            <div className={cn(
              'mt-[5px] h-1.5 w-1.5 flex-none rounded-full',
              alertLevel === 'critical' ? 'bg-rose-500' : alertLevel === 'danger' ? 'bg-amber-500' : 'bg-emerald-500'
            )} />
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-widest text-zinc-600">
                Desk Note
              </p>
              <p
                className={cn(
                  'mt-1 text-[12px] leading-relaxed',
                  alertLevel === 'critical'
                    ? 'text-rose-300/80'
                    : alertLevel === 'danger'
                      ? 'text-amber-300/80'
                      : 'text-zinc-400'
                )}
              >
                {takeaway}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
