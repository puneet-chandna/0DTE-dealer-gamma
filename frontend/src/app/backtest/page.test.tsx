import type { ReactNode } from 'react';
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

import BacktestPage from './page';
import type { DataProviderInfo, VectorBTBacktestResult } from '@/types';

const sampleResult: VectorBTBacktestResult = {
  total_return: 0.1,
  sharpe_ratio: 1.5,
  sortino_ratio: 1.8,
  calmar_ratio: 1.2,
  max_drawdown: -0.05,
  total_trades: 8,
  winning_trades: 5,
  losing_trades: 3,
  win_rate: 0.625,
  profit_factor: 1.9,
  avg_trade_return: 0.012,
  best_trade: 0.04,
  worst_trade: -0.01,
  avg_trade_duration_minutes: 36,
  start_date: '2025-01-01T09:30:00-05:00',
  end_date: '2025-03-01T15:55:00-05:00',
  equity_curve: [100000, 102500, 110000],
};

const { mockUseUIStore, mockUseVectorbtBacktest } = vi.hoisted(() => ({
  mockUseUIStore: vi.fn(() => ({
    demoModeEnabled: false,
    selectedProvider: 'yfinance',
    availableProviders: [] as DataProviderInfo[],
  })),
  mockUseVectorbtBacktest: vi.fn(() => ({
    data: null,
    isLoading: false,
    error: null,
    isFetching: false,
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
  EquityCurveChart: () => <div>Equity Curve Chart</div>,
}));

vi.mock('@/hooks/useAnalyticsData', () => ({
  useVectorbtBacktest: (params: unknown, enabled: boolean) =>
    mockUseVectorbtBacktest(params, enabled),
}));

vi.mock('@/stores/uiStore', () => ({
  useUIStore: mockUseUIStore,
}));

describe('BacktestPage reviewer demo validation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-03-30T16:00:00Z'));
    mockUseUIStore.mockReturnValue({
      demoModeEnabled: false,
      selectedProvider: 'yfinance',
      availableProviders: [] as DataProviderInfo[],
    });
    mockUseVectorbtBacktest.mockImplementation(
      (params: { start_date: string; end_date: string } | null, enabled: boolean) => ({
        data:
          enabled &&
          params?.start_date === '2025-01-01' &&
          params?.end_date === '2025-03-01'
            ? sampleResult
            : null,
        isLoading: false,
        error: null,
        isFetching: false,
      })
    );
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('shows an inline warning for future dates and re-enables the run once the range is valid again', () => {
    render(<BacktestPage />);

    const endDateInput = screen.getByLabelText(/end date/i);
    const runButton = screen.getByRole('button', { name: /run backtest/i });

    fireEvent.change(endDateInput, { target: { value: '2026-03-31' } });

    expect(screen.getByText(/future dates aren't available/i)).toBeInTheDocument();
    expect(runButton).toBeDisabled();

    fireEvent.change(endDateInput, { target: { value: '2026-03-30' } });

    expect(screen.queryByText(/future dates aren't available/i)).not.toBeInTheDocument();
    expect(runButton).not.toBeDisabled();
  });

  it('clears stale results and the chart when the user enters a future date after a successful run', () => {
    render(<BacktestPage />);

    fireEvent.click(screen.getByRole('button', { name: /run backtest/i }));

    expect(screen.getByText('Equity Curve')).toBeInTheDocument();
    expect(screen.getByText('Equity Curve Chart')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/end date/i), {
      target: { value: '2026-03-31' },
    });

    expect(screen.getByText(/future dates aren't available/i)).toBeInTheDocument();
    expect(
      screen.getByText(/configure parameters and run a backtest/i)
    ).toBeInTheDocument();
    expect(screen.queryByText('Equity Curve')).not.toBeInTheDocument();
    expect(screen.queryByText('Equity Curve Chart')).not.toBeInTheDocument();
  });

  it('suppresses demo auto-submit when the default range is in the future versus New York market date', () => {
    vi.setSystemTime(new Date('2024-12-30T16:00:00Z'));
    mockUseUIStore.mockReturnValue({
      demoModeEnabled: true,
      selectedProvider: 'yfinance',
      availableProviders: [] as DataProviderInfo[],
    });

    render(<BacktestPage />);

    expect(screen.getByText(/future dates aren't available/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /run backtest/i })).toBeDisabled();
    expect(
      mockUseVectorbtBacktest.mock.calls.some(([, enabled]) => enabled === true)
    ).toBe(false);
    expect(mockUseVectorbtBacktest).toHaveBeenLastCalledWith(null, false);
  });
});
