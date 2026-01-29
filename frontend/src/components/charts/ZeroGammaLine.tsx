/**
 * ZeroGammaLine - Chart overlay component for Zero Gamma Level
 *
 * Displays as dashed line with label - used as chart annotation.
 * Note: This is a helper component; for Recharts, use ReferenceLine directly.
 */

'use client';

import { memo } from 'react';
import { cn } from '@/lib/utils';
import { formatCurrency } from '@/lib/utils';

interface ZeroGammaLineProps {
  value: number;
  spotPrice?: number;
  className?: string;
}

/**
 * Standalone Zero Gamma Level display (not for chart overlay)
 */
function ZeroGammaLineComponent({ value, spotPrice, className }: ZeroGammaLineProps) {
  // Calculate distance from spot
  const distanceFromSpot = spotPrice ? value - spotPrice : null;
  const distancePercent = spotPrice
    ? ((distanceFromSpot ?? 0) / spotPrice) * 100
    : null;

  // Determine color based on whether we're above or below zero gamma
  const isAboveZeroGamma = spotPrice ? spotPrice > value : false;

  return (
    <div className={cn('flex items-center gap-3', className)}>
      {/* Visual line indicator */}
      <div className="flex items-center gap-1">
        <div className="h-px w-4 border-t-2 border-dashed border-violet-500" />
        <div className="h-2 w-2 rounded-full bg-violet-500" />
        <div className="h-px w-4 border-t-2 border-dashed border-violet-500" />
      </div>

      {/* Value display */}
      <div>
        <div className="flex items-baseline gap-2">
          <span className="text-sm font-medium text-violet-400">Zero Γ</span>
          <span className="text-lg font-bold text-zinc-50">
            {formatCurrency(value, 0)}
          </span>
        </div>
        {distanceFromSpot !== null && distancePercent !== null && (
          <p className="text-xs text-zinc-500">
            {isAboveZeroGamma ? 'Above' : 'Below'} spot by{' '}
            <span
              className={cn(
                'font-medium',
                isAboveZeroGamma ? 'text-emerald-400' : 'text-rose-400'
              )}
            >
              {formatCurrency(Math.abs(distanceFromSpot), 0)} (
              {Math.abs(distancePercent).toFixed(2)}%)
            </span>
          </p>
        )}
      </div>
    </div>
  );
}

export const ZeroGammaLine = memo(ZeroGammaLineComponent);

/**
 * Configuration for Recharts ReferenceLine
 * Use this with <ReferenceLine {...zeroGammaReferenceLineConfig(value)} />
 */
export function zeroGammaReferenceLineConfig(value: number) {
  return {
    x: value,
    stroke: '#a78bfa',
    strokeWidth: 2,
    strokeDasharray: '8 4',
    label: {
      value: `0Γ: $${value.toLocaleString()}`,
      position: 'top' as const,
      fill: '#a78bfa',
      fontSize: 11,
    },
  };
}
