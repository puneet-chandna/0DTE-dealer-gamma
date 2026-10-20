import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { DataContext, SnapshotContext } from './DataContext';
import type { GEXSnapshot } from '@/types';

const snapshot: GEXSnapshot = {
  timestamp: '2026-10-16T15:43:20Z', provider: 'yfinance', spot_price: 7689,
  total_call_gex: 1e9, total_put_gex: -2e9, net_gex: -1e9,
  zero_gamma_level: 7733, dominant_strike: 7680, gex_by_strike: {},
  metrics: { actual_instrument: 'SPY', is_proxy: true, is_replay_data: true },
};

describe('research data context', () => {
  it('distinguishes a historical replay from a stale live capture', () => {
    render(<SnapshotContext snapshot={snapshot} isStale />);
    expect(screen.getByText(/Replay capture: Oct 16, 2026 11:43 AM ET/)).toBeInTheDocument();
    expect(screen.getByText(/SPY.*SPX proxy/)).toBeInTheDocument();
    expect(screen.queryByText(/capture is stale/i)).not.toBeInTheDocument();
  });

  it('identifies actual Yahoo history independently of selected-provider chrome', () => {
    render(<DataContext provenance={{
      provider: 'yfinance', requested_symbol: 'SPY', actual_instrument: 'SPY',
      is_proxy: false, data_kind: 'captured', sample_count: 20,
      actual_start: '2026-10-15T13:30:00Z', actual_end: '2026-10-16T15:00:00Z',
      calculation_versions: [], quality_limitations: [],
    }} />);
    expect(screen.getByText(/Source: Yahoo Finance/)).toBeInTheDocument();
    expect(screen.getByText(/20 captured observations/)).toBeInTheDocument();
    expect(screen.getByText(/Oct 16, 2026 11:00 AM ET/)).toBeInTheDocument();
  });
});

it('does not invent an instrument identity for legacy captures', () => {
  render(<SnapshotContext snapshot={{ ...snapshot, metrics: {} }} />);
  expect(screen.getByText('Instrument identity unavailable')).toBeInTheDocument();
});

it('identifies generated GEX by its actual generator instead of the selected provider', () => {
  render(<SnapshotContext snapshot={{ ...snapshot, provider: 'tradier', metrics: { is_synthetic_data: true } }} />);
  expect(screen.getByText('Source: Demo generator')).toBeInTheDocument();
  expect(screen.queryByText('Source: Tradier')).not.toBeInTheDocument();
});
