import type { ReactNode } from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import AnalyticsPage from './page';
import type { DataProviderInfo } from '@/types';

const { mockUseUIStore } = vi.hoisted(() => ({
  mockUseUIStore: vi.fn(() => ({
    selectedProvider: 'tradier',
    availableProviders: [] as DataProviderInfo[],
  })),
}));

vi.mock('@/components/ui/NavBar', () => ({
  NavBar: () => <div>NavBar</div>,
}));

vi.mock('@/components/ui', () => ({
  Card: ({ children }: { children: ReactNode }) => <section>{children}</section>,
  CardHeader: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  CardContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  CardTitle: ({ children }: { children: ReactNode }) => <h2>{children}</h2>,
  PageShell: ({ children }: { children: ReactNode }) => <main>{children}</main>,
}));

vi.mock('@/components/charts', () => ({
  ChartErrorBoundary: ({ children }: { children: ReactNode }) => <>{children}</>,
  IVSurfaceChart: () => <div>IV Surface Chart</div>,
  IVSkewChart: () => <div>IV Skew Chart</div>,
  TechnicalOverlayChart: () => <div>Technical Overlay Chart</div>,
}));

vi.mock('@/hooks/useAnalyticsData', () => ({
  useIVSurface: () => ({
    data: { spot_price: 5000, count: 0, surface: [], skew: [] },
    isLoading: false,
    error: null,
  }),
  useTechnicalIndicators: vi.fn(() => ({
    data: { data: [], indicators: ['ATR', 'RSI', 'BBANDS'] },
    isLoading: false,
    error: null,
  })),
  useRiskFreeRate: () => ({
    data: { rate_pct: 4.5, is_fallback: false, source: 'FRED' },
  }),
}));

vi.mock('@/stores/uiStore', () => ({
  useUIStore: mockUseUIStore,
}));

describe('AnalyticsPage provider gating', () => {
  it('renders the technical indicators chart for Tradier', () => {
    render(<AnalyticsPage />);

    expect(screen.getByText('Technical Overlay Chart')).toBeInTheDocument();
    expect(
      screen.queryByText(/technical indicators are currently unavailable for tradier/i)
    ).not.toBeInTheDocument();
  });

  it('falls back safely when the persisted provider is unknown', () => {
    mockUseUIStore.mockReturnValue({
      selectedProvider: 'legacy-provider',
      availableProviders: [
        {
          name: 'yfinance',
          display_name: 'Yahoo Finance',
          provides_greeks: false,
          supports_spx_directly: false,
          rate_limit: 10,
          requires_api_key: false,
          is_available: true,
          unavailable_reason: null,
          features: ['spot_price', 'options_chain'],
        },
      ],
    });

    render(<AnalyticsPage />);

    expect(screen.getByText(/provider: yahoo finance/i)).toBeInTheDocument();
  });
});
