import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { Sidebar } from './Sidebar';

const storeState = vi.hoisted(() => ({
  state: {
    isSidebarOpen: true,
    toggleSidebar: vi.fn(),
    alertThreshold: 1.5,
    setAlertThreshold: vi.fn(),
    refreshInterval: 10,
    setAutoRefresh: vi.fn(),
    autoRefreshEnabled: true,
  },
}));

vi.mock('@/stores/uiStore', () => ({
  useUIStore: () => storeState.state,
}));

vi.mock('@/hooks/useAnalyticsData', () => ({
  useRiskFreeRate: () => ({
    data: {
      rate_pct: 4.75,
      is_fallback: false,
    },
  }),
}));

vi.mock('@/components/ui', () => ({
  MetricCard: ({ label, value }: { label: string; value: string }) => (
    <div>{label}: {value}</div>
  ),
  Card: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  CardContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  Skeleton: () => <div>Skeleton</div>,
}));

vi.mock('@/components/charts', () => ({
  RegimeIndicator: () => <div>Regime Indicator</div>,
}));

describe('Sidebar', () => {
  beforeEach(() => {
    storeState.state = {
      isSidebarOpen: true,
      toggleSidebar: vi.fn(),
      alertThreshold: 1.5,
      setAlertThreshold: vi.fn(),
      refreshInterval: 10,
      setAutoRefresh: vi.fn(),
      autoRefreshEnabled: true,
    };
  });

  it('keeps quick stats and settings but does not render page navigation links', () => {
    render(
      <Sidebar
        gexData={{
          net_gex: 1500000000,
          zero_gamma_level: 5600,
          spot_price: 5550,
          dominant_strike: 5575,
        }}
        regimeData={{
          regime: 'long_gamma',
          net_gex_billions: 1.5,
          description: 'Dealers are long gamma',
        }}
      />
    );

    expect(screen.getByText(/quick stats/i)).toBeInTheDocument();
    expect(screen.getByText(/settings/i)).toBeInTheDocument();
    expect(screen.queryByText(/pages/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /analytics/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /dealer flows/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /backtest/i })).not.toBeInTheDocument();
  });
});
