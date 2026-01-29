/**
 * Badge Component - Status badges with color variants
 *
 * Used for regime indicators, live status, etc.
 */

import { type ReactNode } from 'react';
import { cn } from '@/lib/utils';

type BadgeVariant = 'success' | 'danger' | 'warning' | 'neutral' | 'live';

interface BadgeProps {
  children: ReactNode;
  variant?: BadgeVariant;
  className?: string;
  pulse?: boolean;
}

const variantStyles: Record<BadgeVariant, string> = {
  success: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
  danger: 'bg-rose-500/20 text-rose-400 border-rose-500/30',
  warning: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
  neutral: 'bg-zinc-500/20 text-zinc-400 border-zinc-500/30',
  live: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
};

export function Badge({
  children,
  variant = 'neutral',
  className,
  pulse = false,
}: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5',
        'text-xs font-medium',
        'transition-colors duration-200',
        variantStyles[variant],
        className
      )}
    >
      {(pulse || variant === 'live') && (
        <span className="relative flex h-2 w-2">
          <span
            className={cn(
              'absolute inline-flex h-full w-full animate-ping rounded-full opacity-75',
              variant === 'success' || variant === 'live'
                ? 'bg-emerald-400'
                : variant === 'danger'
                  ? 'bg-rose-400'
                  : variant === 'warning'
                    ? 'bg-amber-400'
                    : 'bg-zinc-400'
            )}
          />
          <span
            className={cn(
              'relative inline-flex h-2 w-2 rounded-full',
              variant === 'success' || variant === 'live'
                ? 'bg-emerald-500'
                : variant === 'danger'
                  ? 'bg-rose-500'
                  : variant === 'warning'
                    ? 'bg-amber-500'
                    : 'bg-zinc-500'
            )}
          />
        </span>
      )}
      {children}
    </span>
  );
}
