'use client';

import { memo } from 'react';
import { formatGEX, formatCurrency, formatZeroGammaStatus, hasZeroGammaCrossing } from '@/lib/utils';
import { useRiskFreeRate } from '@/hooks/useAnalyticsData';
import type { GEXSnapshot } from '@/types';

function MetricsPanelComponent({ data, isLoading = false }: { data?: GEXSnapshot | null; isLoading?: boolean }) {
  const { data: rateData } = useRiskFreeRate();
  if (isLoading) return <p role="status" className="panel-caption">Loading breakdown…</p>;
  if (!data) return <p className="panel-caption">No capture available</p>;
  return <dl className="definition-list">
    <dt>Call GEX</dt><dd className={data.total_call_gex < 0 ? 'text-rose-400' : 'text-emerald-400'}>{formatGEX(data.total_call_gex)}</dd>
    <dt>Put GEX</dt><dd className={data.total_put_gex < 0 ? 'text-rose-400' : 'text-emerald-400'}>{formatGEX(data.total_put_gex)}</dd>
    <dt>{hasZeroGammaCrossing(data) ? 'Distance to 0Γ' : '0Γ status'}</dt><dd>{formatZeroGammaStatus(data)}</dd>
    <dt>Dominant strike</dt><dd>{formatCurrency(data.dominant_strike, 0)}</dd>
    <dt>Risk-free rate</dt><dd>{rateData ? `${rateData.rate_pct.toFixed(2)}%` : '—'}</dd>
    {rateData?.is_fallback && <><dt>Rate basis</dt><dd>Fallback</dd></>}
  </dl>;
}
export const MetricsPanel = memo(MetricsPanelComponent);
