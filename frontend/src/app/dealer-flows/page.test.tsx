import type { ReactNode } from 'react';
import { afterEach, describe, it, expect, vi } from 'vitest';
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
  HiddenFlowsPanel: ({ data }: { data?: { net_hidden_flow?: number } | null }) => (
    <div>
      Hidden Flows Panel
      {data ? ` ${data.net_hidden_flow}` : ' no-data'}
    </div>
  ),
  GammaMagnetField: () => <div>Gamma Magnet Field</div>,
  HedgingCascadeSimulator: () => <div>Hedging Cascade Simulator</div>,
}));

vi.mock('@/components/charts', () => ({
  MomentumGauge: ({ data }: { data?: { call_intensity?: number } | null }) => (
    <div>
      Momentum Gauge
      {data ? ` ${data.call_intensity}` : ' no-data'}
    </div>
  ),
  GammaDecayClock: () => <div>Gamma Decay Clock</div>,
}));

describe('DealerFlowsPage source label', () => {
  afterEach(() => {
    mockUseDashboardData.mockReset();
    mockUseDashboardData.mockImplementation(getDefaultDashboardData);
  });

  it('shows the selected provider display name instead of a hardcoded Yahoo label', () => {
    render(<DealerFlowsPage />);

    expect(screen.getByText(/source: tradier/i)).toBeInTheDocument();
  });

  it('shows the snapshot date and Eastern time', () => {
    render(<DealerFlowsPage />);
    expect(screen.getByText(/updated mar 25, 2026 6:30 am et/i)).toBeInTheDocument();
  });

  it.each([
    ['is_replay_data', 'true', /replay capture: mar 25, 2026 6:30 am et/i],
    ['is_persisted_fallback', true, /stored capture: mar 25, 2026 6:30 am et/i],
  ])('preserves %s timestamp provenance', (metric, value, label) => {
    const baseData = getDefaultDashboardData();
    mockUseDashboardData.mockReturnValue({
      ...baseData,
      gexData: { ...baseData.gexData, metrics: { [metric]: value } },
    });
    render(<DealerFlowsPage />);
    expect(screen.getByText(label)).toBeInTheDocument();
    expect(screen.queryByText(/^updated /i)).not.toBeInTheDocument();
  });

  it('treats a zero Hawkes state as valid neutral flow data', () => {
    const baseData = getDefaultDashboardData();
    mockUseDashboardData.mockReturnValue({
      ...baseData,
      gexData: {
        ...baseData.gexData,
        advanced_analytics: {
          charm_vanna: null,
          hawkes: {
            call_intensity: 0,
            put_intensity: 0,
            net_toxicity: 0,
            squeeze_score: 0,
            provider_mode: 'tradier_rich',
            confidence_score: 0,
            event_count: 0,
          },
          smoothed_net_gex: null,
        },
      } as GEXSnapshot,
    });

    render(<DealerFlowsPage />);
    fireEvent.click(screen.getByRole('button', { name: /flow proxy/i }));

    expect(screen.getByText(/snapshot imbalance proxy is balanced/i)).toBeInTheDocument();
    expect(screen.getByText(/heuristic confidence: 0%.*changed contracts: 0/i)).toBeInTheDocument();
  });

  it('distinguishes balanced but elevated Hawkes intensity from quiet flow', () => {
    const baseData = getDefaultDashboardData();
    mockUseDashboardData.mockReturnValue({
      ...baseData,
      gexData: {
        ...baseData.gexData,
        advanced_analytics: {
          charm_vanna: null,
          hawkes: {
            call_intensity: 0.75,
            put_intensity: 0.75,
            net_toxicity: 0,
            squeeze_score: 0.5,
          },
          smoothed_net_gex: null,
        },
      } as GEXSnapshot,
    });

    render(<DealerFlowsPage />);
    fireEvent.click(screen.getByRole('button', { name: /flow proxy/i }));

    expect(screen.getByText(/balanced, but hawkes intensities are elevated on both sides/i)).toBeInTheDocument();
  });

  it('passes demo fallback analytics through to the hidden-flow panels', () => {
    const baseData = getDefaultDashboardData();
    mockUseDashboardData.mockReturnValue({
      ...baseData,
      gexData: {
        ...baseData.gexData,
        advanced_analytics: {
          charm_vanna: {
            charm_flow: 1.2e7,
            vanna_flow: -4.0e6,
            net_hidden_flow: 8.0e6,
            charm_by_strike: {},
            vanna_by_strike: {},
          },
          hawkes: {
            call_intensity: 0.33,
            put_intensity: 0.12,
            net_toxicity: 0.21,
            squeeze_score: 0.27,
          },
          smoothed_net_gex: -4.8e8,
        },
      } as GEXSnapshot,
    });

    render(<DealerFlowsPage />);
    fireEvent.click(screen.getByRole('button', { name: /flow proxy/i }));

    expect(screen.getByText(/Hidden Flows Panel 8000000/)).toBeInTheDocument();
    expect(screen.getByText(/Momentum Gauge 0.33/)).toBeInTheDocument();
  });

  it.each([undefined, Number.NaN])('keeps legacy score %s out of the flow interpretation', (score) => {
    const baseData = getDefaultDashboardData();
    mockUseDashboardData.mockReturnValue({
      ...baseData,
      gexData: {
        ...baseData.gexData,
        advanced_analytics: {
          charm_vanna: null,
          hawkes: {
            call_intensity: 0.75,
            put_intensity: 0.25,
            net_toxicity: 0.5,
            squeeze_score: score,
          },
          smoothed_net_gex: null,
        },
      } as GEXSnapshot,
    });
    render(<DealerFlowsPage />);
    fireEvent.click(screen.getByRole('button', { name: /flow proxy/i }));
    expect(document.body.textContent).not.toContain('NaN');
    expect(screen.getAllByText(/Squeeze score: 0 \/ 100/i).length).toBeGreaterThan(0);
  });
});
