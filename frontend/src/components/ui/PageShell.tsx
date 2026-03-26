import { type ReactNode } from 'react';

import { cn } from '@/lib/utils';

interface PageShellProps {
  children: ReactNode;
  className?: string;
  variant?: 'standard' | 'wide';
}

export function PageShell({
  children,
  className,
  variant = 'standard',
}: PageShellProps) {
  return (
    <main
      className={cn(
        'mx-auto w-full px-4 py-6 sm:px-6 md:py-8 xl:px-8',
        variant === 'wide' ? 'max-w-[1600px]' : 'max-w-[1440px]',
        className
      )}
    >
      {children}
    </main>
  );
}
