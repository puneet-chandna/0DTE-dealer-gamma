'use client';

import { memo, useMemo } from 'react';
import { formatZeroGammaValue, hasZeroGammaCrossing } from '@/lib/utils';
import { Card, CardHeader, CardContent, CardTitle } from '@/components/ui';
import type { GEXSnapshot } from '@/types';

interface GammaMagnetFieldProps {
  data?: GEXSnapshot | null;
  isLoading?: boolean;
}

function formatGex(value: number): string {
  return `${value >= 0 ? '+' : '−'}$${(Math.abs(value) / 1e9).toFixed(2)}B`;
}

function GammaMagnetFieldComponent({ data, isLoading }: GammaMagnetFieldProps) {
  const levels = useMemo(() => Object.entries(data?.gex_by_strike ?? {})
    .map(([strike, gex]) => ({ strike: Number(strike), gex }))
    .filter((point) => Number.isFinite(point.strike) && Number.isFinite(point.gex) && point.gex !== 0)
    .sort((a, b) => Math.abs(b.gex) - Math.abs(a.gex)), [data]);
  const weightedLevel = useMemo(() => {
    if (!data || !Number.isFinite(data.spot_price) || data.spot_price <= 0) return null;
    let weightedSum = 0;
    let totalWeight = 0;
    for (const point of levels) {
      if (point.gex > 0) {
        // Preserve the original distance-weighted heuristic; it does not model price attraction.
        const weight = point.gex / Math.pow(Math.abs(point.strike - data.spot_price) + 5, 1.5);
        weightedSum += point.strike * weight;
        totalWeight += weight;
      }
    }
    return totalWeight > 0 ? weightedSum / totalWeight : null;
  }, [data, levels]);
  const totalAbsolute = levels.reduce((sum, point) => sum + Math.abs(point.gex), 0);

  return (
    <Card>
      <CardHeader><CardTitle>GEX concentration</CardTitle></CardHeader>
      <CardContent className="space-y-5">
        {isLoading || !data ? <p className="text-sm text-[var(--text-secondary)]">{isLoading ? 'Loading strike concentrations…' : 'Awaiting GEX data'}</p> : levels.length ? (
          <>
            <dl className="grid grid-cols-3 gap-4 border-b border-[var(--stroke)] pb-4 text-sm">
              <div><dt className="text-[var(--text-secondary)]">Spot</dt><dd className="mt-1 font-semibold tabular-nums text-[var(--text-primary)]">${data.spot_price.toFixed(2)}</dd></div>
              <div><dt className="text-[var(--text-secondary)]">Zero gamma</dt><dd className="mt-1 font-semibold tabular-nums text-[var(--text-primary)]">{hasZeroGammaCrossing(data) && Number.isFinite(data.zero_gamma_level) ? `$${data.zero_gamma_level.toFixed(2)}` : formatZeroGammaValue(data)}</dd></div>
              <div><dt className="text-[var(--text-secondary)]">Weighted positive-GEX level</dt><dd className="mt-1 font-semibold tabular-nums text-[var(--text-primary)]">{weightedLevel !== null ? `$${weightedLevel.toFixed(2)}` : 'No positive GEX'}</dd></div>
            </dl>
            <table className="w-full text-left text-sm tabular-nums">
              <caption className="pb-3 text-left text-[var(--text-secondary)]">Largest absolute exposures · top {Math.min(5, levels.length)} of {levels.length} strikes</caption>
              <thead className="text-[var(--text-secondary)]"><tr><th className="pb-2 font-medium">Strike ($)</th><th className="pb-2 text-right font-medium">Signed GEX</th><th className="pb-2 text-right font-medium">Share of |GEX|</th></tr></thead>
              <tbody>{levels.slice(0, 5).map((point) => (
                <tr key={point.strike} className="border-t border-[var(--stroke)]">
                  <td className="py-3 text-[var(--text-primary)]">{point.strike.toFixed(2)}</td>
                  <td className={`py-3 text-right font-medium ${point.gex < 0 ? 'text-[var(--negative)]' : 'text-[var(--positive)]'}`}>{formatGex(point.gex)}</td>
                  <td className="py-3 text-right text-[var(--text-secondary)]">{(Math.abs(point.gex) / totalAbsolute * 100).toFixed(1)}%</td>
                </tr>
              ))}</tbody>
            </table>
            <p className="text-sm leading-6 text-[var(--text-secondary)]">Signed hedge notional per 1% spot move. The weighted level uses positive GEX / (|strike − spot| + 5)<sup>1.5</sup>; it summarizes the snapshot under the inventory-sign convention and does not predict a destination for price.</p>
          </>
        ) : <p className="text-sm text-[var(--text-secondary)]">No nonzero strike exposures in this capture.</p>}
      </CardContent>
    </Card>
  );
}

export const GammaMagnetField = memo(GammaMagnetFieldComponent);
