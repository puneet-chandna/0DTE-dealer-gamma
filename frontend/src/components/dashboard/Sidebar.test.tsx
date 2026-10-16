import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { Sidebar } from './Sidebar';
import type { GEXSnapshot, RegimeData } from '@/types';

const sampleGex: GEXSnapshot = {
  timestamp: '2026-03-30T16:00:00Z',
  net_gex: 1500000000,
  total_call_gex: 2000000000,
  total_put_gex: -500000000,
  zero_gamma_level: 5600,
  spot_price: 5550,
  dominant_strike: 5575,
  gex_by_strike: {},
  metrics: {},
};

const sampleRegime: RegimeData = {
  timestamp: sampleGex.timestamp,
  regime: 'long_gamma',
  net_gex: sampleGex.net_gex,
  net_gex_billions: 1.5,
  description: 'Dealers are long gamma',
  color: 'green',
};

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

describe('Sidebar layout variants', () => {
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

  it('renders stack mode as a full-width section instead of a left rail', () => {
    const { container } = render(
      <Sidebar
        layout="stack"
        gexData={sampleGex}
        regimeData={sampleRegime}
      />
    );

    expect(screen.getByText(/quick stats/i)).toBeInTheDocument();
    expect(container.firstChild).toHaveClass('w-full');
    expect(container.firstChild).not.toHaveClass('w-72');
    expect(screen.getByText(/settings/i)).toBeInTheDocument();
    expect(screen.queryByText(/pages/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /analytics/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /dealer flows/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /backtest/i })).not.toBeInTheDocument();
  });

  it('labels zero gamma as below range when no in-range crossing exists', () => {
    render(
      <Sidebar
        layout="stack"
        gexData={{
          ...sampleGex,
          zero_gamma_level: 5200,
          spot_price: 6420,
          dominant_strike: 6400,
          metrics: {
            zero_gamma_crossing_found: false,
            zero_gamma_relation: 'below_range',
          },
        }}
        regimeData={sampleRegime}
      />
    );

    expect(screen.getByText(/zero gamma: below range/i)).toBeInTheDocument();
  });

  it('names the sidebar toggle and exposes its expanded state', () => {
    const { rerender } = render(<Sidebar />);
    const toggle = screen.getByRole('button', { name: /collapse sidebar/i });
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    fireEvent.click(toggle);
    expect(storeState.state.toggleSidebar).toHaveBeenCalledOnce();

    storeState.state.isSidebarOpen = false;
    rerender(<Sidebar isLoading />);
    expect(screen.getByRole('button', { name: /expand sidebar/i })).toHaveAttribute('aria-expanded', 'false');
  });

  it('labels the alert threshold in dollar billions and exposes the selected refresh interval', () => {
    render(<Sidebar />);
    const threshold = screen.getByRole('slider', { name: /alert threshold \(\$b\)/i });
    expect(threshold).toHaveAttribute('aria-valuetext', '1.50 billion dollars');
    fireEvent.change(threshold, { target: { value: '2' } });
    expect(storeState.state.setAlertThreshold).toHaveBeenCalledWith(2);
    expect(screen.getByRole('button', { name: '10s' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: '5s' })).toHaveAttribute('aria-pressed', 'false');
  });
});
