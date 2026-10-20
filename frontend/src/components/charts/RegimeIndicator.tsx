/**
 * RegimeIndicator - Visual regime status component
 *
 * Static indicator of the signed GEX proxy regime.
 */

'use client';

import { memo } from 'react';
import { TrendingUp, TrendingDown, Activity } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { RegimeType } from '@/types';

interface RegimeIndicatorProps {
  regime: RegimeType;
  netGexBillions?: number;
  description?: string;
  compact?: boolean;
}

const regimeConfig: Record<
  RegimeType,
  {
    icon: typeof Activity;
    label: string;
    description: string;
    bgClass: string;
    textClass: string;
  }
> = {
  short_gamma: {
    icon: TrendingDown,
    label: 'Short Gamma',
    description: 'Negative signed GEX proxy',
    bgClass: 'bg-[var(--negative)]',
    textClass: 'text-[var(--negative)]',
  },
  long_gamma: {
    icon: TrendingUp,
    label: 'Long Gamma',
    description: 'Positive signed GEX proxy',
    bgClass: 'bg-[var(--positive)]',
    textClass: 'text-[var(--positive)]',
  },
  neutral: {
    icon: Activity,
    label: 'Neutral',
    description: 'GEX proxy near the regime threshold',
    bgClass: 'bg-[var(--warning)]',
    textClass: 'text-[var(--warning)]',
  },
};

function RegimeIndicatorComponent({
  regime,
  netGexBillions,
  description,
  compact = false,
}: RegimeIndicatorProps) {
  const config = regimeConfig[regime];
  const Icon = config.icon;

  if (compact) {
    return (
      <div className="flex items-center gap-2">
        <div
          key={regime}
          className={cn(
            'h-3 w-3 rounded-full',
            config.bgClass
          )}
        />
        <span className={cn('text-sm font-medium', config.textClass)}>
          {config.label}
        </span>
      </div>
    );
  }

  return (
    <div
      key={regime}
      className="flex items-center gap-4"
    >
      <div>
        <div
          className={cn(
            'flex h-12 w-12 items-center justify-center rounded-lg',
            config.bgClass
          )}
        >
          <Icon className="h-6 w-6 text-[var(--surface-base)]" />
        </div>
      </div>

      {/* Text content */}
      <div>
        <div className="flex items-baseline gap-2">
          <h3 className={cn('text-lg font-bold', config.textClass)}>
            {config.label}
          </h3>
          {netGexBillions !== undefined && (
            <span className="text-sm text-[var(--text-secondary)]">
              ({netGexBillions >= 0 ? '+' : ''}
              {netGexBillions.toFixed(2)}B)
            </span>
          )}
        </div>
        <p className="text-sm text-[var(--text-secondary)]">
          {description || config.description}
        </p>
      </div>
    </div>
  );
}

export const RegimeIndicator = memo(RegimeIndicatorComponent);
