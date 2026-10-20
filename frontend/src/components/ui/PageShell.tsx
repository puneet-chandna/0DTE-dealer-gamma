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
      id="research-content"
      className={cn(
        'research-page w-full',
        variant === 'wide' ? 'max-w-[1920px]' : 'max-w-[1800px]',
        className
      )}
    >
      {children}
    </main>
  );
}
