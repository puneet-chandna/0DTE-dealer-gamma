'use client';

import { memo, useId } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useUIStore } from '@/stores/uiStore';
import { MetricsPanel } from './MetricsPanel';
import type { GEXSnapshot, RegimeData } from '@/types';

interface SidebarProps { gexData?: GEXSnapshot | null; regimeData?: RegimeData | null; isLoading?: boolean; layout?: 'rail' | 'stack' }
function SidebarComponent({ gexData, isLoading = false }: SidebarProps) {
  const thresholdId = useId();
  const { isSidebarOpen, toggleSidebar, alertThreshold, setAlertThreshold, refreshInterval, setAutoRefresh, autoRefreshEnabled } = useUIStore();
  return <aside className={`inspector research-panel ${isSidebarOpen ? '' : 'collapsed'}`} aria-label="Research inspector">
    <div className="inspector-heading">
      {isSidebarOpen && <h2>Inspector</h2>}
      <button type="button" className="control-button" onClick={toggleSidebar} aria-label={isSidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'} aria-expanded={isSidebarOpen}>{isSidebarOpen ? <ChevronRight size={15} /> : <ChevronLeft size={15} />}</button>
    </div>
    {isSidebarOpen && <>
      <section className="inspector-section"><h3>Exposure breakdown</h3><MetricsPanel data={gexData} isLoading={isLoading} /></section>
      <section className="inspector-section space-y-4"><h3>Monitoring</h3>
        <div><label htmlFor={thresholdId}>Alert Threshold ($B)</label><div className="mt-2 flex items-center gap-3"><input id={thresholdId} type="range" min="0.5" max="3" step="0.25" value={alertThreshold} aria-valuetext={`${alertThreshold.toFixed(2)} billion dollars`} onChange={e => setAlertThreshold(Number(e.target.value))} className="min-w-0 flex-1 accent-blue-400" /><span className="tabular-nums">{alertThreshold.toFixed(2)}B</span></div>
          {gexData && Math.abs(gexData.net_gex / 1e9) >= alertThreshold && <p className="mt-2 text-amber-300">Absolute GEX exceeds this visual alert threshold.</p>}
        </div>
        <div><p className="mb-2">Polling interval</p><div className="flex gap-1" role="group" aria-label="Polling interval">{[5, 10, 30, 60].map(seconds => <button type="button" key={seconds} className="control-button flex-1" aria-pressed={refreshInterval === seconds} onClick={() => setAutoRefresh(autoRefreshEnabled, seconds)}>{seconds}s</button>)}</div></div>
      </section>
      <section className="inspector-section"><h3>Model assumptions</h3><p>Baseline inventory: calls positive, puts negative. Open interest does not identify dealer positions.</p><details className="source-details mt-3"><summary>Calculation & source limits</summary><p>GEX is hedge notional per 1% spot move. Zero gamma holds each contract’s IV fixed. Daily open interest and provider quote timestamps can differ; capture time does not establish quote freshness.</p></details></section>
    </>}
  </aside>;
}
export const Sidebar = memo(SidebarComponent);
