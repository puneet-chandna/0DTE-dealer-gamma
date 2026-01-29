/**
 * Skeleton Component - Loading state placeholders
 *
 * Animated pulse effect for loading states.
 */

import { cn } from '@/lib/utils';

interface SkeletonProps {
  className?: string;
}

export function Skeleton({ className }: SkeletonProps) {
  return (
    <div
      className={cn(
        'animate-pulse rounded-md bg-zinc-800',
        className
      )}
    />
  );
}

/**
 * Pre-defined skeleton variants for common use cases
 */

export function SkeletonText({ className }: SkeletonProps) {
  return <Skeleton className={cn('h-4 w-full', className)} />;
}

export function SkeletonTitle({ className }: SkeletonProps) {
  return <Skeleton className={cn('h-6 w-1/2', className)} />;
}

export function SkeletonValue({ className }: SkeletonProps) {
  return <Skeleton className={cn('h-8 w-32', className)} />;
}

export function SkeletonChart({ className }: SkeletonProps) {
  return <Skeleton className={cn('h-64 w-full', className)} />;
}

interface SkeletonCardProps {
  className?: string;
  showHeader?: boolean;
}

export function SkeletonCard({ className, showHeader = true }: SkeletonCardProps) {
  return (
    <div
      className={cn(
        'rounded-xl border border-zinc-800 bg-zinc-900/80',
        className
      )}
    >
      {showHeader && (
        <div className="border-b border-zinc-800 px-5 py-4">
          <SkeletonTitle />
        </div>
      )}
      <div className="space-y-3 px-5 py-4">
        <SkeletonValue />
        <SkeletonText className="w-3/4" />
      </div>
    </div>
  );
}
