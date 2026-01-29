/**
 * AlertBanner Component - Regime alerts banner
 *
 * Displays Short Gamma (danger), Long Gamma (success), or Neutral warnings.
 */

'use client';

import { cn } from '@/lib/utils';
import { motion, AnimatePresence } from 'framer-motion';
import { AlertTriangle, TrendingUp, TrendingDown, Activity } from 'lucide-react';
import type { RegimeType } from '@/types';

interface AlertBannerProps {
  regime: RegimeType;
  description?: string;
  netGexBillions?: number;
  isVisible?: boolean;
  onDismiss?: () => void;
}

const regimeConfig: Record<
  RegimeType,
  {
    icon: typeof AlertTriangle;
    title: string;
    bgClass: string;
    borderClass: string;
    textClass: string;
    iconClass: string;
  }
> = {
  short_gamma: {
    icon: TrendingDown,
    title: 'Short Gamma',
    bgClass: 'bg-rose-500/10',
    borderClass: 'border-rose-500/30',
    textClass: 'text-rose-400',
    iconClass: 'text-rose-500',
  },
  long_gamma: {
    icon: TrendingUp,
    title: 'Long Gamma',
    bgClass: 'bg-emerald-500/10',
    borderClass: 'border-emerald-500/30',
    textClass: 'text-emerald-400',
    iconClass: 'text-emerald-500',
  },
  neutral: {
    icon: Activity,
    title: 'Neutral',
    bgClass: 'bg-amber-500/10',
    borderClass: 'border-amber-500/30',
    textClass: 'text-amber-400',
    iconClass: 'text-amber-500',
  },
};

export function AlertBanner({
  regime,
  description,
  netGexBillions,
  isVisible = true,
  onDismiss,
}: AlertBannerProps) {
  const config = regimeConfig[regime];
  const Icon = config.icon;

  // Only show banner prominently for short_gamma (high volatility warning)
  const shouldShowProminent = regime === 'short_gamma';

  return (
    <AnimatePresence>
      {isVisible && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: 'auto' }}
          exit={{ opacity: 0, height: 0 }}
          transition={{ duration: 0.3, ease: 'easeInOut' }}
          className={cn(
            'overflow-hidden rounded-lg border',
            config.bgClass,
            config.borderClass
          )}
        >
          <div className="flex items-center gap-3 px-4 py-3">
            <Icon
              className={cn(
                'h-5 w-5 flex-shrink-0',
                config.iconClass,
                shouldShowProminent && 'animate-pulse'
              )}
            />
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <span className={cn('font-semibold', config.textClass)}>
                  {config.title}
                </span>
                {netGexBillions !== undefined && (
                  <span className={cn('text-sm', config.textClass)}>
                    ({netGexBillions >= 0 ? '+' : ''}
                    {netGexBillions.toFixed(2)}B)
                  </span>
                )}
              </div>
              {description && (
                <p className="mt-0.5 text-sm text-zinc-400">{description}</p>
              )}
            </div>
            {onDismiss && (
              <button
                onClick={onDismiss}
                className={cn(
                  'rounded-md p-1 transition-colors',
                  'hover:bg-zinc-800 focus:outline-none focus:ring-2 focus:ring-zinc-600'
                )}
                aria-label="Dismiss alert"
              >
                <span className="sr-only">Dismiss</span>
                <svg
                  className="h-4 w-4 text-zinc-500"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M6 18L18 6M6 6l12 12"
                  />
                </svg>
              </button>
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/**
 * Default descriptions for each regime
 */
export const regimeDescriptions: Record<RegimeType, string> = {
  short_gamma: 'Dealers are short gamma. Volatility amplification expected.',
  long_gamma: 'Dealers are long gamma. Volatility dampening expected.',
  neutral: 'Near neutral gamma positioning. Normal volatility expected.',
};
