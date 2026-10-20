import { formatMarketTimestamp } from '@/lib/utils';
import type { DataProvenance, GEXSnapshot, SnapshotMetricValue } from '@/types';

const providerName = (provider?: string) => provider === 'yfinance' ? 'Yahoo Finance' : provider === 'tradier' ? 'Tradier' : provider ?? 'Unknown source';
const flag = (value?: SnapshotMetricValue) => value === true || value === 1 || (typeof value === 'string' && ['true', '1', 'yes', 'on'].includes(value.toLowerCase()));

export function DataContext({ provenance }: { provenance?: DataProvenance | null }) {
  if (!provenance) return <p className="panel-caption">Awaiting source metadata</p>;
  return <div className="data-context" aria-label="Data provenance">
    <span className={`data-kind ${provenance.data_kind === 'synthetic' ? 'synthetic' : ''}`}>{provenance.data_kind === 'synthetic' ? 'Synthetic scenario' : provenance.is_replay ? 'Captured replay' : 'Captured data'}</span>
    <span>{provenance.actual_instrument}{provenance.is_proxy ? ` · ${provenance.requested_symbol} proxy` : ''}</span>
    <span>Source: {provenance.data_kind === 'synthetic' ? 'Demo generator' : providerName(provenance.provider)}</span>
    <span>{provenance.sample_count} {provenance.data_kind} observations</span>
    {provenance.actual_end && <time dateTime={provenance.actual_end}>{formatMarketTimestamp(provenance.actual_end)}</time>}
    <details className="source-details"><summary>Source details</summary><p>Clock basis: {provenance.timestamp_basis ?? 'capture reference; quote freshness unknown'}</p>{provenance.quality_limitations.map(limit => <p key={limit}>{limit}</p>)}</details>
  </div>;
}

export function SnapshotContext({ snapshot, isStale = false }: { snapshot: GEXSnapshot | null; isStale?: boolean }) {
  if (!snapshot) return <div className="data-context">Awaiting a usable market capture</div>;
  const replay = flag(snapshot.metrics?.is_replay_data);
  const synthetic = flag(snapshot.metrics?.is_synthetic_data) || flag(snapshot.metrics?.is_mock);
  const stored = flag(snapshot.metrics?.is_persisted_fallback);
  const label = synthetic ? 'Synthetic scenario:' : replay ? 'Replay capture:' : stored ? 'Stored capture:' : 'Capture:';
  return <div className="data-context" aria-label="Snapshot provenance">
    <span className={`data-kind ${synthetic ? 'synthetic' : ''}`}>{synthetic ? 'Synthetic scenario' : replay ? 'Captured replay' : stored ? 'Stored capture' : 'Provider capture'}</span>
    <span>{String(snapshot.metrics?.actual_instrument ?? 'Instrument identity unavailable')}{flag(snapshot.metrics?.is_proxy) ? ' · SPX proxy' : ''}</span>
    <span>Source: {synthetic ? 'Demo generator' : providerName(snapshot.provider)}</span>
    <time dateTime={snapshot.timestamp}>{label} {formatMarketTimestamp(snapshot.timestamp)}</time>
    {isStale && !replay && !synthetic && <span className="text-amber-300">Capture is stale</span>}
  </div>;
}
