'use client';

import { useMemo } from 'react';
import { Clock3 } from 'lucide-react';
import { useMarketStatus } from '@/hooks/useMarketStatus';
import type { MarketStatusType } from '@/types';

const marketStatusCopy: Record<MarketStatusType, { title: string; message: string }> = {
  open: {
    title: 'US Market Open',
    message: 'Live market data is active.',
  },
  pre_market: {
    title: 'Market Closed',
    message: 'Pre-market is active. Live 0DTE data resumes at the opening bell.',
  },
  after_hours: {
    title: 'Market Closed',
    message: 'After-hours session is active. Live 0DTE data will resume at the next open.',
  },
  closed_weekend: {
    title: 'Weekend Closure',
    message: 'US markets are closed for the weekend. Demo mode stays available for reviews.',
  },
};

export function MarketStatusAlert() {
  const { data: marketStatus } = useMarketStatus();

  const content = useMemo(() => {
    if (!marketStatus || marketStatus.is_open) {
      return null;
    }

    const copy = marketStatusCopy[marketStatus.status];
    return {
      title: copy.title,
      detail: marketStatus.next_open
        ? `${copy.message} Next open: ${marketStatus.next_open}.`
        : copy.message,
    };
  }, [marketStatus]);

  if (!content) {
    return null;
  }

  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-50 max-w-sm">
      <div className="pointer-events-auto rounded-2xl border border-amber-400/25 bg-zinc-950/95 px-4 py-3 shadow-2xl shadow-amber-950/30 ring-1 ring-black/30 backdrop-blur">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 flex h-9 w-9 items-center justify-center rounded-full bg-amber-500/12 text-amber-300">
            <Clock3 className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-amber-200">{content.title}</p>
            <p className="mt-1 text-xs leading-5 text-zinc-300">{content.detail}</p>
          </div>
        </div>
      </div>
    </div>
  );
}
