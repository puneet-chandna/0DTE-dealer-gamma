'use client';

import { useState, useMemo, useRef } from 'react';
import { NavBar } from '@/components/ui/NavBar';
import { PageShell } from '@/components/ui/PageShell';
import { SnapshotContext } from '@/components/ui/DataContext';
import { HiddenFlowsPanel, GammaMagnetField, HedgingCascadeSimulator } from '@/components/dashboard';
import { MomentumGauge, GammaDecayClock } from '@/components/charts';
import { useDashboardData } from '@/hooks/useDashboardData';
import { formatZeroGammaValue, hasZeroGammaCrossing } from '@/lib/utils';
import type { GEXSnapshot, CharmVannaSnapshot, HawkesState } from '@/types';

// ============================================================================
// Constants
// ============================================================================

type TabId = 'magnetics' | 'cascade' | 'decay' | 'hidden';

const TABS: { id: TabId; label: string; question: string }[] = [
  { id: 'magnetics', label: 'GEX concentration', question: 'Signed exposure by strike; the weighted level is a heuristic, not a price target.' },
  { id: 'cascade', label: 'Cascade Scenario', question: 'Fixed-gamma hedge adjustment under an assumed spot shock and liquidity.' },
  { id: 'decay', label: 'Time sensitivity', question: 'An ATM, fixed-volatility time illustration anchored to the displayed capture.' },
  { id: 'hidden', label: 'Flow proxy (Hawkes-style)', question: 'Snapshot changes and Greek sensitivities; these are not observed dealer orders.' },
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
    hero = `The positive-GEX weighted level is ${pullTarget.toFixed(0)} — ${Math.abs(pullDirection).toFixed(0)} points ${pullDirection > 0 ? 'above' : 'below'} spot. This distance-weighted proxy does not predict price attraction.`;
  } else {
    hero = `The positive-GEX weighted level is near spot, or positive GEX is absent. This heuristic does not establish a directional bias.`;
  }

  const bullets: string[] = [];
  if (attractors.length > 0) {
    bullets.push(`${attractors.length} positive-GEX strikes. If the baseline inventory signs reflect dealer exposure, hedging would oppose small spot moves. Largest: ${attractors[0].strike.toFixed(0)} with ${formatB(attractors[0].gex)} GEX.`);
  }
  if (repellers.length > 0) {
    bullets.push(`${repellers.length} negative-GEX strikes. Under the same inventory assumption, hedging would follow small spot moves. Largest: ${repellers[0].strike.toFixed(0)} with ${formatB(repellers[0].gex)} GEX.`);
  }
  bullets.push(`Dominant strike: ${data.dominant_strike.toFixed(0)} — highest absolute GEX concentration.`);
  if (hasZeroGammaCrossing(data) && data.zero_gamma_level > 0) {
    const zglRelative = data.zero_gamma_level - data.spot_price;
    bullets.push(`Modeled zero gamma: ${data.zero_gamma_level.toFixed(0)} — ${Math.abs(zglRelative).toFixed(0)} pts ${zglRelative > 0 ? 'above' : 'below'} spot. The root assumes fixed contract IV and inventory signs.`);
  }

  let takeaway = '';
  if (isLongGamma && Math.abs(pullDirection) > 10) {
    takeaway = `The proxy is consistent with counter-move hedging near ${pullTarget.toFixed(0)} under fixed gamma and inventory assumptions. It does not establish support, resistance, or a profitable strategy.`;
  } else if (data.net_gex < 0) {
    takeaway = `A negative-GEX proxy is consistent with hedging in the direction of spot moves under the baseline inventory assumption. Real impact also depends on liquidity, position changes, and other flows.`;
  } else {
    takeaway = `GEX alone does not establish price direction or a profitable strategy. Compare the proxy with independent market and liquidity data.`;
  }

  return { hero, bullets, takeaway };
}

function getCascadeInterpretation(data: GEXSnapshot | null) {
  if (!data) return null;

  const isLongGamma = data.net_gex > 0;
  const netGexB = data.net_gex / 1e9;

  let hero = '';
  if (isLongGamma) {
    hero = `The GEX proxy is positive (${netGexB.toFixed(2)}B). If the assumed dealer inventory signs hold, delta-neutral hedging would oppose a small spot move.`;
  } else {
    hero = data.net_gex < 0
      ? `The GEX proxy is negative (${netGexB.toFixed(2)}B). If the assumed dealer inventory signs hold, delta-neutral hedging would follow a small spot move.`
      : `The net GEX proxy is zero. The fixed-gamma scenario has no net hedge adjustment; this does not establish low market risk.`;
  }

  const bullets: string[] = [];
  bullets.push(isLongGamma
    ? `Positive modeled dealer gamma implies selling after a rise and buying after a fall, with other inputs held fixed.`
    : `Negative modeled dealer gamma implies buying after a rise and selling after a fall, with other inputs held fixed. Zero net gamma implies no first-order net adjustment.`
  );
  bullets.push(`Net GEX: ${formatB(data.net_gex)} of hedge notional per 1% spot move under the baseline call-positive/put-negative convention, not measured dealer inventory.`);
  bullets.push(`The slider illustrates fixed-gamma feedback with uncalibrated liquidity and at most six rounds. Its price impacts are not forecasts.`);
  bullets.push(`Open interest does not identify dealer inventory, hedge execution, or available market depth. GEX alone cannot estimate crash or squeeze probabilities.`);

  let takeaway = '';
  if (isLongGamma) {
    takeaway = `Counter-move hedging is a conditional mechanism, not evidence of low flash-crash risk or an advantage for option sellers.`;
  } else if (data.net_gex < 0) {
    takeaway = `With-move hedging can reinforce a shock under the assumed inventory and liquidity conditions. This proxy does not establish a trade recommendation or quantify that risk.`;
  } else {
    takeaway = `Zero net GEX gives no net first-order hedge adjustment in this scenario. Offsetting positions, other Greeks, and unrelated flows can still affect prices.`;
  }

  return { hero, bullets, takeaway };
}

function getDecayInterpretation(data: GEXSnapshot | null) {
  if (!data) return null;

  return {
    hero: 'The time factor is frozen to the capture shown here. It holds volatility fixed and the option at the money; it does not estimate aggregate gamma or volatility risk.',
    bullets: [
      'At the money, gamma scales approximately as 1/√T with other inputs fixed. The displayed factor uses a 390-minute opening baseline.',
      'The illustration uses weekday 09:30–16:00 ET hours. Holidays, early closes and contract-specific expiries are not resolved.',
    ],
    takeaway: 'Outside the illustration interval the factor is unavailable, not zero. Actual gamma also depends on moneyness, volatility and inventory.',
  };
}

function getHiddenFlowsInterpretation(
  charm_vanna: CharmVannaSnapshot | null | undefined,
  hawkes: HawkesState | null | undefined,
) {
  const hasCharmVanna = charm_vanna && (charm_vanna.charm_flow !== 0 || charm_vanna.vanna_flow !== 0);
  const hasHawkes = hawkes !== null && hawkes !== undefined;

  if (!hasCharmVanna && !hasHawkes) return null;

  const squeezeScore = Number.isFinite(hawkes?.squeeze_score) ? hawkes!.squeeze_score : 0;

  let hero = '';
  const bullets: string[] = [];
  let takeaway = '';

  if (hasCharmVanna) {
    const netFlow = charm_vanna!.net_hidden_flow;
    const isPositive = netFlow >= 0;
    const charmDominant = Math.abs(charm_vanna!.charm_flow) > Math.abs(charm_vanna!.vanna_flow);

    hero = `The signed-inventory scenario estimates ${formatM(netFlow)} in net hedge notional — a ${isPositive ? 'buy' : 'sell'} adjustment at fixed spot. `;
    hero += charmDominant ? `Time decay (Charm) is the primary driver.` : `Volatility sensitivity (Vanna) is the primary driver.`;

    bullets.push(`Charm flow: ${formatM(charm_vanna!.charm_flow)} — hedging pressure from time decay in the next 30 minutes.`);
    bullets.push(`Vanna flow: ${formatM(charm_vanna!.vanna_flow)} — hedge notional if implied volatility drops one percentage point.`);
    bullets.push(`Net hidden flow: ${formatM(netFlow)} — ${isPositive ? 'buy' : 'sell'} scenario, not observed orders.`);
  }

  if (hasHawkes) {
    const squeeze = Math.round(squeezeScore * 100);
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
        ? `Snapshot imbalance proxy is balanced. Hawkes intensities are low in this capture, so there is no active call or put dominance.`
        : isBalancedButElevated
          ? `Snapshot imbalance proxy is balanced, but Hawkes intensities are elevated on both sides. Squeeze score: ${squeeze} / 100.`
        : `Snapshot imbalance proxy is ${callDominant ? 'call-dominant' : 'put-dominant'}. Squeeze score: ${squeeze} / 100.`;
    }

    bullets.push(`Call intensity: ${hawkes!.call_intensity.toFixed(2)} — ${hasBalancedFlow ? 'balanced with puts' : callDominant ? 'dominant' : 'subordinate'} side.`);
    bullets.push(`Put intensity: ${hawkes!.put_intensity.toFixed(2)} — ${hasBalancedFlow ? 'balanced with calls' : putDominant ? 'dominant' : 'subordinate'} side.`);
    bullets.push(`Squeeze score: ${squeeze} / 100 — ${squeeze > 60 ? 'high — elevated proxy imbalance' : squeeze > 40 ? 'moderate — watch for buildup' : isBalanced ? 'low — low snapshot imbalance' : isBalancedButElevated ? 'low — balanced flow is elevated on both sides' : 'low — low proxy imbalance'}.`);
  }

  if (hasCharmVanna) {
    const isPositive = charm_vanna!.net_hidden_flow >= 0;
    takeaway = isPositive
      ? `Positive scenario hedge notional under fixed spot and signed inventory; this does not establish a price floor.`
      : `Negative scenario hedge notional under fixed spot and signed inventory; price impact has not been validated.`;
  } else {
    takeaway = `Hawkes-style intensities summarize the snapshot proxy. ${squeezeScore > 0.5 ? 'Elevated snapshot imbalance; the squeeze score is an uncalibrated heuristic.' : 'A low score does not establish low market risk.'}`;
  }

  return { hero, bullets, takeaway };
}

// ============================================================================
// Summary Bar Helpers
// ============================================================================

function getRegimeLabel(netGex: number): { text: string; color: string } {
  if (netGex > 0) return { text: 'Positive GEX proxy', color: 'text-emerald-400' };
  if (netGex < 0) return { text: 'Negative GEX proxy', color: 'text-rose-400' };
  return { text: 'Zero net GEX', color: 'text-zinc-300' };
}

function getBias(data: GEXSnapshot): { text: string; color: string } {
  if (data.net_gex > 0) return { text: 'Counter-move proxy', color: 'text-zinc-300' };
  if (data.net_gex < 0) return { text: 'With-move proxy', color: 'text-rose-400' };
  return { text: 'No net adjustment', color: 'text-zinc-300' };
}

// ============================================================================
// Page Component
// ============================================================================

export default function DealerFlowsPage() {
  const { gexData, isLoading, isStale, error } = useDashboardData();
  const [activeTab, setActiveTab] = useState<TabId>('magnetics');
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const interpretation = useMemo(() => activeTab === 'magnetics' ? getMagneticsInterpretation(gexData) : activeTab === 'cascade' ? getCascadeInterpretation(gexData) : activeTab === 'decay' ? getDecayInterpretation(gexData) : getHiddenFlowsInterpretation(gexData?.advanced_analytics?.charm_vanna, gexData?.advanced_analytics?.hawkes), [activeTab, gexData]);
  const regime = gexData ? getRegimeLabel(gexData.net_gex) : null;
  const bias = gexData ? getBias(gexData) : null;
  const hawkes = gexData?.advanced_analytics?.hawkes;

  return <div className="min-h-screen"><NavBar /><PageShell variant="wide">
    <div className="page-heading"><div><h1>Dealer Flows</h1><p>Positioning proxies and conditional hedging scenarios</p></div><span className="panel-caption">Models · assumptions explicit</span></div>
    <div className="context-strip"><SnapshotContext snapshot={gexData} isStale={isStale} /></div>
    {error && <p role="alert" className="research-alert mb-4">{gexData ? 'Refresh unavailable; retaining the labelled capture.' : 'Market capture unavailable. Choose Demo to explore a labelled replay or synthetic scenario.'}</p>}
    <dl className="metric-strip">
      <div><dt>Spot reference</dt><dd>{gexData ? gexData.spot_price.toFixed(2) : '—'}</dd></div>
      <div><dt>Inventory convention</dt><dd className={regime?.color}>{regime?.text ?? '—'}</dd></div>
      <div><dt>Modeled hedge response</dt><dd className={bias?.color}>{bias?.text ?? '—'}</dd></div>
      <div><dt>Zero gamma</dt><dd>{formatZeroGammaValue(gexData)}</dd></div>
    </dl>
    <div className="research-tabs" role="tablist" aria-label="Hedging models">{TABS.map((tab, index) => <button type="button" key={tab.id} role="tab" id={`tab-${tab.id}`} aria-selected={activeTab === tab.id} aria-controls={`panel-${tab.id}`} tabIndex={activeTab === tab.id ? 0 : -1} ref={node => { tabRefs.current[index] = node; }} onClick={() => setActiveTab(tab.id)} onKeyDown={event => {
      const next = event.key === 'ArrowRight' ? (index + 1) % TABS.length : event.key === 'ArrowLeft' ? (index + TABS.length - 1) % TABS.length : event.key === 'Home' ? 0 : event.key === 'End' ? TABS.length - 1 : null;
      if (next === null) return;
      event.preventDefault(); setActiveTab(TABS[next].id); tabRefs.current[next]?.focus();
    }}>{tab.label}</button>)}</div>
    <section role="tabpanel" id={`panel-${activeTab}`} aria-labelledby={`tab-${activeTab}`} tabIndex={0}>
      <p className="panel-caption mb-4">{TABS.find(tab => tab.id === activeTab)!.question}</p>
      <div className="model-workspace">
        <div className="min-w-0">
          {activeTab === 'magnetics' && <GammaMagnetField data={gexData} isLoading={isLoading} />}
          {activeTab === 'cascade' && <HedgingCascadeSimulator data={gexData} isLoading={isLoading} />}
          {activeTab === 'decay' && <GammaDecayClock data={gexData} isLoading={isLoading} />}
          {activeTab === 'hidden' && <>
            <div className="grid grid-cols-2 gap-5"><HiddenFlowsPanel data={gexData?.advanced_analytics?.charm_vanna} isLoading={isLoading} /><MomentumGauge data={hawkes} isLoading={isLoading} /></div>
            {Boolean(gexData?.metrics?.advanced_analytics_synthetic) && <p className="panel-caption mt-3">Backfilled analytics: this replay capture predates these fields, so charm, vanna, Hawkes and smoothed-level values are derived from the demo generator instead of the captured option chain.</p>}
            {hawkes && <p className="panel-caption mt-3">Flow proxy{hawkes.provider_mode ? ` · mode: ${hawkes.provider_mode}` : ''}{typeof hawkes.confidence_score === 'number' ? ` · heuristic confidence: ${(hawkes.confidence_score * 100).toFixed(0)}%` : ''}{typeof hawkes.event_count === 'number' ? ` · changed contracts: ${hawkes.event_count}` : ''}. Snapshot estimate; confidence is uncalibrated and contract changes are not trades.</p>}
          </>}
        </div>
        <aside className="model-notes research-panel" aria-label="Model interpretation">
          <div className="panel-heading"><h2>Interpretation & limits</h2></div>
          <div className="panel-content model-interpretation">
            {isLoading && <p role="status">Loading capture…</p>}
            {interpretation ? <><p className="text-zinc-100">{interpretation.hero}</p><ul className="mt-4 space-y-3">{interpretation.bullets.slice(0, 2).map(bullet => <li key={bullet}>{bullet}</li>)}</ul><details className="source-details mt-4"><summary>Assumptions & details</summary>{interpretation.bullets.slice(2).map(bullet => <p key={bullet}>{bullet}</p>)}<p>{interpretation.takeaway}</p></details></> : !isLoading && <p>No usable model inputs for this capture.</p>}
          </div>
        </aside>
      </div>
    </section>
    <p className="panel-caption mt-5">Baseline calls-positive / puts-negative inventory is assumed. These models do not measure dealer positions, executed orders, or probabilities of future price moves.</p>
  </PageShell></div>;
}
