'use client';

import { useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useProviders } from '@/hooks/useProviders';
import { useUIStore } from '@/stores/uiStore';

export function AppShellEffects() {
  const queryClient = useQueryClient();
  const { demoModeEnabled, selectedProvider } = useUIStore();
  const previousModeRef = useRef(demoModeEnabled);
  const previousProviderRef = useRef(selectedProvider);

  useProviders();

  useEffect(() => {
    const root = document.documentElement;
    root.dataset.theme = 'dark';
    root.classList.add('dark');
    root.style.colorScheme = 'dark';
  }, []);

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

  return null;
}
