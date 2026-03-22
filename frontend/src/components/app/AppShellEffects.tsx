'use client';

import { useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { MarketStatusAlert } from '@/components/ui/MarketStatusAlert';
import { useUIStore } from '@/stores/uiStore';

export function AppShellEffects() {
  const queryClient = useQueryClient();
  const { demoModeEnabled } = useUIStore();
  const previousModeRef = useRef(demoModeEnabled);

  useEffect(() => {
    if (previousModeRef.current === demoModeEnabled) {
      return;
    }

    previousModeRef.current = demoModeEnabled;

    queryClient.invalidateQueries({
      predicate: (query) => {
        const rootKey = query.queryKey[0];
        return rootKey === 'gex' || rootKey === 'analytics' || rootKey === 'iv-surface' || rootKey === 'technical-indicators' || rootKey === 'vectorbt-backtest';
      },
    });
  }, [demoModeEnabled, queryClient]);

  return <MarketStatusAlert />;
}
