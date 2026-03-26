/**
 * Card Component - Generic card wrapper with consistent styling
 *
 * RULE: Use this as the base container for dashboard widgets.
 */

import { type ReactNode } from 'react';
import { cn } from '@/lib/utils';

interface CardProps {
  children: ReactNode;
  className?: string;
}

export function Card({ children, className }: CardProps) {
  return (
    <div
      className={cn(
        'rounded-xl border border-zinc-800 bg-zinc-900/80 backdrop-blur-sm',
        'shadow-lg shadow-black/20',
        'transition-all duration-200',
        className
      )}
    >
      {children}
    </div>
  );
}

interface CardHeaderProps {
  children: ReactNode;
  className?: string;
}

export function CardHeader({ children, className }: CardHeaderProps) {
  return (
    <div
      className={cn(
        'border-b border-zinc-800 px-4 py-3 sm:px-5 sm:py-4',
        className
      )}
    >
      {children}
    </div>
  );
}

interface CardContentProps {
  children: ReactNode;
  className?: string;
}

export function CardContent({ children, className }: CardContentProps) {
  return (
    <div className={cn('px-4 py-3 sm:px-5 sm:py-4', className)}>
      {children}
    </div>
  );
}

interface CardFooterProps {
  children: ReactNode;
  className?: string;
}

export function CardFooter({ children, className }: CardFooterProps) {
  return (
    <div
      className={cn(
        'border-t border-zinc-800 px-4 py-3 sm:px-5',
        className
      )}
    >
      {children}
    </div>
  );
}

interface CardTitleProps {
  children: ReactNode;
  className?: string;
}

export function CardTitle({ children, className }: CardTitleProps) {
  return (
    <h3 className={cn('text-sm font-medium text-zinc-400', className)}>
      {children}
    </h3>
  );
}
