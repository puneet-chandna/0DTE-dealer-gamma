import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider, focusManager, onlineManager } from '@tanstack/react-query';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import BacktestPage from './page';
import type { VectorBTBacktestResult } from '@/types';

const { runBacktest, store } = vi.hoisted(() => ({
  runBacktest: vi.fn(),
  store: { demoModeEnabled: false, selectedProvider: 'yfinance' },
}));

vi.mock('@/lib/api', () => ({ analyticsAPI: { runVectorbtBacktest: runBacktest } }));
vi.mock('@/stores/uiStore', () => ({ useUIStore: () => store }));
vi.mock('@/components/ui/NavBar', () => ({ NavBar: () => null }));
vi.mock('@/components/charts', () => ({
  ChartErrorBoundary: ({ children }: { children: ReactNode }) => children,
  EquityCurveChart: () => null,
}));

const sampleResult: VectorBTBacktestResult = {
  total_return: 0.1, sharpe_ratio: 1.5, sortino_ratio: 1.8, calmar_ratio: 1.2,
  max_drawdown: -0.05, total_trades: 8, winning_trades: 5, losing_trades: 3,
  win_rate: 0.625, profit_factor: 1.9, avg_trade_return: 0.012, best_trade: 0.04,
  worst_trade: -0.01, avg_trade_duration_minutes: 36, start_date: '2025-01-01',
  end_date: '2025-01-01', equity_curve: [100000, 110000],
};

let client: QueryClient;

function renderPage() {
  return render(
    <QueryClientProvider client={client}><BacktestPage /></QueryClientProvider>
  );
}

async function runAndExpect(returnText: string) {
  fireEvent.click(screen.getByRole('button', { name: 'Run Backtest' }));
  await screen.findByText(returnText);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Run Backtest' })).toBeEnabled());
}

beforeEach(() => {
  vi.clearAllMocks();
  store.demoModeEnabled = false;
  store.selectedProvider = 'yfinance';
  runBacktest.mockResolvedValue(sampleResult);
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  focusManager.setFocused(true);
  onlineManager.setOnline(true);
});

afterEach(() => {
  cleanup();
  client.clear();
  focusManager.setFocused(undefined);
});

describe('BacktestPage submitted query cache', () => {
  it.each([
    ['Initial Cash', '0', '100000', { initial_cash: 100000 }],
    ['Allocation (%)', '101', '50', { position_size: 0.5 }],
  ])('rejects a direct submit with invalid %s before running corrected parameters', async (label, invalid, valid, expected) => {
    renderPage();
    expect(runBacktest).not.toHaveBeenCalled();
    const input = screen.getByLabelText(label);
    const form = input.closest('form')!;
    fireEvent.change(input, { target: { value: invalid } });
    await act(async () => { fireEvent.submit(form); });
    expect(runBacktest).not.toHaveBeenCalled();

    fireEvent.change(input, { target: { value: valid } });
    expect(runBacktest).not.toHaveBeenCalled();
    fireEvent.submit(form);
    await screen.findByText('10.00%');
    expect(runBacktest).toHaveBeenCalledExactlyOnceWith(
      expect.objectContaining(expected), { demo: false, provider: 'yfinance' }
    );
  });

  it('fetches updated captures when the same parameters are explicitly run again', async () => {
    renderPage();
    expect(runBacktest).not.toHaveBeenCalled();
    await runAndExpect('10.00%');

    await act(async () => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
      onlineManager.setOnline(false);
      onlineManager.setOnline(true);
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(runBacktest).toHaveBeenCalledTimes(1);

    runBacktest.mockResolvedValue({ ...sampleResult, total_return: 0.2 });
    await runAndExpect('20.00%');
    expect(runBacktest).toHaveBeenCalledTimes(2);
    expect(runBacktest.mock.calls[1]).toEqual(runBacktest.mock.calls[0]);
  });

  it('refreshes previously cached parameters only after the user submits them again', async () => {
    renderPage();
    await runAndExpect('10.00%');
    const cashInput = screen.getByLabelText('Initial Cash');
    fireEvent.change(cashInput, { target: { value: '200000' } });
    expect(runBacktest).toHaveBeenCalledTimes(1);
    expect(screen.getByText('10.00%')).toBeInTheDocument();

    runBacktest.mockResolvedValue({ ...sampleResult, total_return: 0.2 });
    await runAndExpect('20.00%');
    fireEvent.change(cashInput, { target: { value: '100000' } });
    expect(runBacktest).toHaveBeenCalledTimes(2);
    expect(screen.getByText('20.00%')).toBeInTheDocument();

    runBacktest.mockResolvedValue({ ...sampleResult, total_return: 0.3 });
    await runAndExpect('30.00%');
    expect(runBacktest).toHaveBeenCalledTimes(3);
    expect(runBacktest.mock.calls[2]).toEqual(runBacktest.mock.calls[0]);
  });
});
