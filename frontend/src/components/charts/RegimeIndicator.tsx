/**
 * RegimeIndicator - Visual regime status component
 *
 * Large colored indicator with animation when regime changes.
 */

'use client';

import { memo } from 'react';
import { motion } from 'framer-motion';
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
    glowClass: string;
  }
> = {
  short_gamma: {
    icon: TrendingDown,
    label: 'Short Gamma',
    description: 'Volatility amplification expected',
    bgClass: 'bg-rose-500',
    textClass: 'text-rose-400',
    glowClass: 'shadow-rose-500/30',
  },
  long_gamma: {
    icon: TrendingUp,
    label: 'Long Gamma',
    description: 'Volatility dampening expected',
    bgClass: 'bg-emerald-500',
    textClass: 'text-emerald-400',
    glowClass: 'shadow-emerald-500/30',
  },
  neutral: {
    icon: Activity,
    label: 'Neutral',
    description: 'Normal volatility expected',
    bgClass: 'bg-amber-500',
    textClass: 'text-amber-400',
    glowClass: 'shadow-amber-500/30',
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
        <motion.div
          key={regime}
          initial={{ scale: 0.8, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ type: 'spring', stiffness: 300, damping: 20 }}
          className={cn(
            'h-3 w-3 rounded-full shadow-lg',
            config.bgClass,
            config.glowClass
          )}
        />
        <span className={cn('text-sm font-medium', config.textClass)}>
          {config.label}
        </span>
      </div>
    );
  }

  return (
    <motion.div
      key={regime}
      initial={{ scale: 0.95, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ type: 'spring', stiffness: 300, damping: 20 }}
      className="flex items-center gap-4"
    >
      {/* Pulsing indicator */}
      <div className="relative">
        <motion.div
          animate={{
            scale: [1, 1.2, 1],
            opacity: [0.5, 0.8, 0.5],
          }}
          transition={{
            duration: 2,
            repeat: Infinity,
            ease: 'easeInOut',
          }}
          className={cn(
            'absolute inset-0 rounded-full blur-md',
            config.bgClass
          )}
        />
        <div
          className={cn(
            'relative flex h-12 w-12 items-center justify-center rounded-full shadow-lg',
            config.bgClass,
            config.glowClass
          )}
        >
          <Icon className="h-6 w-6 text-white" />
        </div>
      </div>

      {/* Text content */}
      <div>
        <div className="flex items-baseline gap-2">
          <h3 className={cn('text-lg font-bold', config.textClass)}>
            {config.label}
          </h3>
          {netGexBillions !== undefined && (
            <span className="text-sm text-zinc-400">
              ({netGexBillions >= 0 ? '+' : ''}
              {netGexBillions.toFixed(2)}B)
            </span>
          )}
        </div>
        <p className="text-sm text-zinc-500">
          {description || config.description}
        </p>
      </div>
    </motion.div>
  );
}

export const RegimeIndicator = memo(RegimeIndicatorComponent);
