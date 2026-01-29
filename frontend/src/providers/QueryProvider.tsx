'use client';

/**
 * 0DTE GEX Frontend - React Query Provider
 *
 * Provides QueryClient configuration for server state management.
 * RULE: All API data should flow through React Query, not Zustand.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';

interface QueryProviderProps {
  children: ReactNode;
}

/**
 * React Query Provider with optimized configuration for GEX data.
 *
 * Configuration rationale:
 * - staleTime: 10s - GEX data is time-sensitive but doesn't need sub-second freshness
 * - gcTime: 5min - Keep unused data in cache for quick navigation
 * - refetchOnWindowFocus: true - Update when user returns to tab
 * - retry: 2 - Retry failed requests twice before error
 */
export function QueryProvider({ children }: QueryProviderProps) {
  // Create QueryClient instance per component mount to avoid SSR hydration issues
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            // Data is considered fresh for 10 seconds
            staleTime: 10 * 1000,
            // Keep unused data in cache for 5 minutes
            gcTime: 5 * 60 * 1000,
            // Retry failed requests twice
            retry: 2,
            // Exponential backoff for retries
            retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
            // Refetch on window focus for fresh data
            refetchOnWindowFocus: true,
            // Don't refetch on reconnect - WebSocket handles this
            refetchOnReconnect: false,
          },
          mutations: {
            // Retry mutations once
            retry: 1,
          },
        },
      })
  );

  return (
    <QueryClientProvider client={queryClient}>
      {children}
    </QueryClientProvider>
  );
}

export default QueryProvider;
