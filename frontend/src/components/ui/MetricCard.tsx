/**
 * MetricCard Component - Display single metric with trend
 *
 * Used for Net GEX, Zero Gamma Level, Spot Price, etc.
 */

import { type ReactNode } from 'react';
import { cn } from '@/lib/utils';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { Card, CardContent } from './Card';
import { Skeleton } from './Skeleton';

type TrendDirection = 'up' | 'down' | 'neutral';

interface MetricCardProps {
  label: string;
  value: string | number;
  subtext?: string;
  trend?: TrendDirection;
  trendValue?: string;
  isLoading?: boolean;
  isNegative?: boolean;
  isPositive?: boolean;
  className?: string;
  icon?: ReactNode;
}

const trendStyles: Record<TrendDirection, string> = {
  up: 'text-emerald-400',
  down: 'text-rose-400',
  neutral: 'text-zinc-500',
};

const TrendIcon = ({ direction }: { direction: TrendDirection }) => {
  const iconClass = 'h-3.5 w-3.5';
  switch (direction) {
    case 'up':
      return <TrendingUp className={iconClass} />;
    case 'down':
      return <TrendingDown className={iconClass} />;
    default:
      return <Minus className={iconClass} />;
  }
};

export function MetricCard({
  label,
  value,
  subtext,
  trend,
  trendValue,
  isLoading = false,
  isNegative = false,
  isPositive = false,
  className,
  icon,
}: MetricCardProps) {
  // Determine value color based on positive/negative flags
  const valueColor = isNegative
    ? 'text-rose-400'
    : isPositive
      ? 'text-emerald-400'
      : 'text-zinc-50';

  if (isLoading) {
    return (
      <Card className={className}>
        <CardContent className="space-y-2">
          <Skeleton className="h-4 w-20" />
          <Skeleton className="h-8 w-32" />
          {subtext !== undefined && <Skeleton className="h-3.5 w-24" />}
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className={cn('group hover:border-zinc-700', className)}>
      <CardContent>
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-zinc-400">{label}</span>
          {icon && <span className="text-zinc-500">{icon}</span>}
        </div>

        <div className="mt-2 flex items-baseline gap-2">
          <span className={cn('text-2xl font-bold tracking-tight', valueColor)}>
            {value}
          </span>
          {trend && (
            <span
              className={cn(
                'flex items-center gap-0.5 text-xs font-medium',
                trendStyles[trend]
              )}
            >
              <TrendIcon direction={trend} />
              {trendValue}
            </span>
          )}
        </div>

        {subtext && (
          <p className="mt-1 text-xs text-zinc-500">{subtext}</p>
        )}
      </CardContent>
    </Card>
  );
}
