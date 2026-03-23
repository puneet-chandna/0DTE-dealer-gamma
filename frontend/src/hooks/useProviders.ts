import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { dataAPI } from '@/lib/api';
import { useUIStore } from '@/stores/uiStore';
import type { ProvidersResponse } from '@/types';

export const providerQueryKeys = {
  all: ['providers'] as const,
};

export function useProviders() {
  const { setAvailableProviders } = useUIStore();

  const query = useQuery<ProvidersResponse>({
    queryKey: providerQueryKeys.all,
    queryFn: dataAPI.getProviders,
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });

  useEffect(() => {
    if (!query.data) {
      return;
    }

    setAvailableProviders(query.data.providers, query.data.active_default);
  }, [query.data, setAvailableProviders]);

  return query;
}
