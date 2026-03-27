import type { ReactNode } from 'react';
import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

import DealerFlowsPage from './page';
import type { DataProviderInfo, GEXSnapshot } from '@/types';

const { mockUseUIStore, mockUseDashboardData, getDefaultDashboardData } = vi.hoisted(() => {
  const getDefaultDashboardData = () => ({
    gexData: {
      timestamp: '2026-03-25T10:30:00.000Z',
      spot_price: 6025,
      total_call_gex: -2.0e9,
      total_put_gex: 1.5e9,
      net_gex: -5.0e8,
      zero_gamma_level: 6015,
      gex_by_strike: { 6000: 2.0e8, 6025: -3.0e8 },
      dominant_strike: 6025,
      metrics: {},
      advanced_analytics: null,
    } as GEXSnapshot,
    regimeData: null,
    strikesData: null,
    isRealtime: false,
    connectionState: 'connected' as const,
    isLoading: false,
    isStale: false,
    error: null,
    lastUpdateTime: Date.parse('2026-03-25T10:30:00.000Z'),
    retryCount: 0,
    reconnect: vi.fn(),
    disconnect: vi.fn(),
  });

  return {
  mockUseUIStore: vi.fn(() => ({
    selectedProvider: 'tradier',
    availableProviders: [
      {
        name: 'tradier',
        display_name: 'Tradier',
        provides_greeks: true,
        supports_spx_directly: true,
        rate_limit: 120,
        requires_api_key: true,
        is_available: true,
        unavailable_reason: null,
        features: ['spot_price', 'options_chain', 'greeks'],
      },
    ] as DataProviderInfo[],
  })),
  mockUseDashboardData: vi.fn(getDefaultDashboardData),
  getDefaultDashboardData,
  };
});

vi.mock('@/stores/uiStore', () => ({
  useUIStore: mockUseUIStore,
}));

vi.mock('@/hooks/useDashboardData', () => ({
  useDashboardData: mockUseDashboardData,
}));

vi.mock('@/components/ui/NavBar', () => ({
  NavBar: () => <div>NavBar</div>,
}));

vi.mock('@/components/ui/PageShell', () => ({
  PageShell: ({ children }: { children: ReactNode }) => <main>{children}</main>,
}));

vi.mock('@/components/dashboard', () => ({
  HiddenFlowsPanel: () => <div>Hidden Flows Panel</div>,
  GammaMagnetField: () => <div>Gamma Magnet Field</div>,
  HedgingCascadeSimulator: () => <div>Hedging Cascade Simulator</div>,
}));

vi.mock('@/components/charts', () => ({
  MomentumGauge: () => <div>Momentum Gauge</div>,
  GammaDecayClock: () => <div>Gamma Decay Clock</div>,
}));

describe('DealerFlowsPage source label', () => {
  it('shows the selected provider display name instead of a hardcoded Yahoo label', () => {
    render(<DealerFlowsPage />);

    expect(screen.getByText(/source: tradier/i)).toBeInTheDocument();
  });

  it('treats a zero Hawkes state as valid neutral flow data', () => {
    const baseData = getDefaultDashboardData();
    mockUseDashboardData.mockImplementation(() => ({
      ...baseData,
      gexData: {
        ...baseData.gexData,
        advanced_analytics: {
          charm_vanna: null,
          hawkes: {
            call_intensity: 0,
            put_intensity: 0,
            net_toxicity: 0,
            squeeze_probability: 0,
          },
          smoothed_net_gex: null,
        },
      } as GEXSnapshot,
    }));

    render(<DealerFlowsPage />);
    fireEvent.click(screen.getByRole('button', { name: /hidden flows/i }));

    expect(screen.getByText(/order flow momentum is balanced/i)).toBeInTheDocument();
    mockUseDashboardData.mockImplementation(getDefaultDashboardData);
  });
});
