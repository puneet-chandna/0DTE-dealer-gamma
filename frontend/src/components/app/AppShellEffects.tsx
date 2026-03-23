'use client';

import { useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { MarketStatusAlert } from '@/components/ui/MarketStatusAlert';
import { useProviders } from '@/hooks/useProviders';
import { useUIStore } from '@/stores/uiStore';

export function AppShellEffects() {
  const queryClient = useQueryClient();
  const { demoModeEnabled, selectedProvider } = useUIStore();
  const previousModeRef = useRef(demoModeEnabled);
  const previousProviderRef = useRef(selectedProvider);

  useProviders();

  useEffect(() => {
    if (
      previousModeRef.current === demoModeEnabled &&
      previousProviderRef.current === selectedProvider
    ) {
      return;
    }

    previousModeRef.current = demoModeEnabled;
    previousProviderRef.current = selectedProvider;

    queryClient.invalidateQueries({
      predicate: (query) => {
        const rootKey = query.queryKey[0];
        return rootKey === 'gex' || rootKey === 'analytics' || rootKey === 'iv-surface' || rootKey === 'technical-indicators' || rootKey === 'vectorbt-backtest';
      },
    });
  }, [demoModeEnabled, queryClient, selectedProvider]);

  return <MarketStatusAlert />;
}
