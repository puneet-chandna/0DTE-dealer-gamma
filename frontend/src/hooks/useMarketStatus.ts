'use client';

import { useQuery } from '@tanstack/react-query';
import { dataAPI } from '@/lib/api';
import { queryKeys } from '@/hooks/useGEXData';
import type { MarketStatus } from '@/types';

export function useMarketStatus() {
  return useQuery<MarketStatus>({
    queryKey: queryKeys.marketStatus,
    queryFn: dataAPI.getMarketStatus,
    refetchInterval: 1000,
    staleTime: 0,
    retry: 2,
  });
}
