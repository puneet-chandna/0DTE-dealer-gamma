import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import AnalyticsPage from './page';

vi.mock('@/components/ui/NavBar', () => ({
  NavBar: () => <div>NavBar</div>,
}));

vi.mock('@/components/ui', () => ({
  Card: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
  CardHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CardContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CardTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
}));

vi.mock('@/components/charts', () => ({
  ChartErrorBoundary: ({ children }: { children: React.ReactNode }) => <>{children}</>,
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
  useUIStore: () => ({
    selectedProvider: 'tradier',
  }),
}));

describe('AnalyticsPage provider gating', () => {
  it('shows an explicit technical-indicator unavailable message for Tradier', () => {
    render(<AnalyticsPage />);

    expect(
      screen.getByText(/technical indicators are currently unavailable for tradier/i)
    ).toBeInTheDocument();
  });
});
