/**
 * Backtest Page — VectorBT strategy backtester with equity curve.
 *
 * Layout:
 * ┌─────────────────────────────────────────────────────────────┐
 * │  NavBar                                                      │
 * ├──────────────────────┬──────────────────────────────────────┤
 * │  Controls            │  Results Summary                     │
 * │  • Date Range        │  (metrics cards)                     │
 * │  • Thresholds        │                                      │
 * │  [Run Backtest]      │                                      │
 * ├──────────────────────┴──────────────────────────────────────┤
 * │  Equity Curve                                                │
 * └─────────────────────────────────────────────────────────────┘
 */

'use client';

import { useEffect, useRef, useState, useCallback, useReducer } from 'react';
import { NavBar } from '@/components/ui/NavBar';
import { Card, CardHeader, CardContent, CardTitle, PageShell } from '@/components/ui';
import { ChartErrorBoundary, EquityCurveChart } from '@/components/charts';
import { useVectorbtBacktest } from '@/hooks/useAnalyticsData';
import { cn, getCurrentMarketDateString, isFutureMarketDate } from '@/lib/utils';
import { useUIStore } from '@/stores/uiStore';

interface BacktestParams {
  start_date: string;
  end_date: string;
  entry_threshold: number;
  exit_threshold: number;
  initial_cash: number;
}

interface BacktestRunState {
  submitted: BacktestParams | null;
  runEnabled: boolean;
}

type BacktestRunAction =
  | { type: 'submit'; params: BacktestParams }
  | { type: 'auto-submit-demo'; params: BacktestParams }
  | { type: 'clear' };

function formatPct(value: number): string {
  return `${(value * 100).toFixed(2)}%`;
}

function backtestRunReducer(
  state: BacktestRunState,
  action: BacktestRunAction
): BacktestRunState {
  if (action.type === 'clear') {
    if (state.submitted === null && !state.runEnabled) {
      return state;
    }

    return {
      submitted: null,
      runEnabled: false,
    };
  }

  return {
    submitted: { ...action.params },
    runEnabled: true,
  };
}

export default function BacktestPage() {
  const { demoModeEnabled } = useUIStore();
  const [params, setParams] = useState<BacktestParams>({
    start_date: '2025-01-01',
    end_date: '2025-03-01',
    entry_threshold: -1e9,
    exit_threshold: 0,
    initial_cash: 100000,
  });

  const [runState, dispatchRun] = useReducer(backtestRunReducer, {
    submitted: null,
    runEnabled: false,
  });
  const autoStartedDemoRef = useRef(false);

  const { data: result, isLoading, error, isFetching } = useVectorbtBacktest(
    runState.submitted,
    runState.runEnabled
  );

  const marketToday = getCurrentMarketDateString();
  const futureDateError =
    isFutureMarketDate(params.start_date, marketToday) ||
    isFutureMarketDate(params.end_date, marketToday)
      ? `Future dates aren't available for backtests. Choose a date on or before ${marketToday} (New York market date).`
      : null;
  const handleRun = useCallback(() => {
    if (futureDateError || !params.start_date || !params.end_date) {
      return;
    }

    dispatchRun({ type: 'submit', params });
  }, [futureDateError, params]);

  const isRunning = isLoading || isFetching;
  const canRunBacktest = !isRunning && !futureDateError && !!params.start_date && !!params.end_date;

  useEffect(() => {
    if (!futureDateError) {
      return;
    }

    dispatchRun({ type: 'clear' });
  }, [futureDateError]);

  useEffect(() => {
    if (!demoModeEnabled) {
      autoStartedDemoRef.current = false;
      return;
    }

    if (
      futureDateError ||
      !params.start_date ||
      !params.end_date ||
      autoStartedDemoRef.current ||
      runState.submitted !== null
    ) {
      return;
    }

    autoStartedDemoRef.current = true;
    dispatchRun({ type: 'auto-submit-demo', params });
  }, [demoModeEnabled, futureDateError, params, runState.submitted]);

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-50">
      <NavBar />

      <PageShell variant="standard">
        {/* Page Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold tracking-tight">Strategy Backtester</h1>
          <p className="mt-1 text-sm text-zinc-400">
            GEX signal-based backtesting powered by vectorbt
          </p>
        </div>

        {/* Controls + Results Row */}
        <div className="mb-6 grid gap-6 xl:grid-cols-[380px_minmax(0,1fr)]">
          {/* Controls Panel */}
          <Card>
            <CardHeader>
              <CardTitle>Parameters</CardTitle>
            </CardHeader>
            <CardContent className="space-y-5">
              {/* Date Range */}
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div>
                  <label
                    htmlFor="backtest-start-date"
                    className="text-xs font-medium text-zinc-400 block mb-1.5"
                  >
                    Start Date
                  </label>
                  <input
                    id="backtest-start-date"
                    type="date"
                    value={params.start_date}
                    onChange={(e) => setParams((p) => ({ ...p, start_date: e.target.value }))}
                    className="w-full rounded-lg border border-zinc-700 bg-zinc-800/60 px-3 py-2 text-sm text-zinc-200 focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500/30"
                  />
                </div>
                <div>
                  <label
                    htmlFor="backtest-end-date"
                    className="text-xs font-medium text-zinc-400 block mb-1.5"
                  >
                    End Date
                  </label>
                  <input
                    id="backtest-end-date"
                    type="date"
                    value={params.end_date}
                    onChange={(e) => setParams((p) => ({ ...p, end_date: e.target.value }))}
                    className="w-full rounded-lg border border-zinc-700 bg-zinc-800/60 px-3 py-2 text-sm text-zinc-200 focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500/30"
                  />
                </div>
              </div>

              {futureDateError && (
                <div className="rounded-lg border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
                  {futureDateError}
                </div>
              )}

              {/* Thresholds */}
              <div>
                <label className="text-xs font-medium text-zinc-400 block mb-1.5">
                  Entry Threshold (GEX $)
                </label>
                <input
                  type="number"
                  value={params.entry_threshold}
                  onChange={(e) =>
                    setParams((p) => ({ ...p, entry_threshold: parseFloat(e.target.value) || -1e9 }))
                  }
                  className="w-full rounded-lg border border-zinc-700 bg-zinc-800/60 px-3 py-2 text-sm text-zinc-200 focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500/30 font-mono"
                  step={1e8}
                />
                <p className="mt-1 text-xs text-zinc-500">Enter long when GEX drops below this</p>
              </div>

              <div>
                <label className="text-xs font-medium text-zinc-400 block mb-1.5">
                  Exit Threshold (GEX $)
                </label>
                <input
                  type="number"
                  value={params.exit_threshold}
                  onChange={(e) =>
                    setParams((p) => ({ ...p, exit_threshold: parseFloat(e.target.value) || 0 }))
                  }
                  className="w-full rounded-lg border border-zinc-700 bg-zinc-800/60 px-3 py-2 text-sm text-zinc-200 focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500/30 font-mono"
                  step={1e8}
                />
              </div>

              <div>
                <label className="text-xs font-medium text-zinc-400 block mb-1.5">
                  Initial Cash
                </label>
                <input
                  type="number"
                  value={params.initial_cash}
                  onChange={(e) =>
                    setParams((p) => ({ ...p, initial_cash: parseFloat(e.target.value) || 100000 }))
                  }
                  className="w-full rounded-lg border border-zinc-700 bg-zinc-800/60 px-3 py-2 text-sm text-zinc-200 focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500/30 font-mono"
                  step={10000}
                />
              </div>

              {/* Run Button */}
              <button
                onClick={handleRun}
                disabled={!canRunBacktest}
                className={cn(
                  'w-full rounded-lg py-2.5 text-sm font-semibold transition-all',
                  isRunning
                    ? 'cursor-wait bg-violet-500/30 text-violet-300'
                    : canRunBacktest
                      ? 'bg-violet-500 text-white hover:bg-violet-600 active:bg-violet-700'
                      : 'cursor-not-allowed bg-zinc-800 text-zinc-500'
                )}
              >
                {isRunning ? (
                  <span className="flex items-center justify-center gap-2">
                    <span className="h-4 w-4 animate-spin rounded-full border-2 border-violet-200 border-t-transparent" />
                    Running Backtest...
                  </span>
                ) : (
                  'Run Backtest'
                )}
              </button>

              {error && !futureDateError && (
                <div className="rounded-lg border border-rose-500/20 bg-rose-500/10 px-3 py-2 text-xs text-rose-400">
                  {error.message}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Results Summary */}
          <div>
            <Card className="h-full">
              <CardHeader>
                <CardTitle>Results Summary</CardTitle>
              </CardHeader>
              <CardContent>
                {!result && !isRunning ? (
                  <div className="flex min-h-[220px] items-center justify-center sm:min-h-[280px] lg:min-h-[340px]">
                    <div className="text-center">
                      <p className="text-sm text-zinc-500">Configure parameters and run a backtest</p>
                      <p className="mt-1 text-xs text-zinc-600">
                        Strategy: Long when Net GEX {'<'} entry threshold, exit when {'>'} exit threshold
                      </p>
                    </div>
                  </div>
                ) : isRunning ? (
                  <div className="flex min-h-[220px] items-center justify-center sm:min-h-[280px] lg:min-h-[340px]">
                    <div className="h-8 w-8 animate-spin rounded-full border-2 border-zinc-600 border-t-violet-400" />
                  </div>
                ) : result ? (
                  <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-4">
                    <MetricTile
                      label="Total Return"
                      value={formatPct(result.total_return)}
                      color={result.total_return >= 0 ? 'positive' : 'negative'}
                    />
                    <MetricTile label="Sharpe Ratio" value={result.sharpe_ratio.toFixed(2)} />
                    <MetricTile label="Sortino Ratio" value={result.sortino_ratio.toFixed(2)} />
                    <MetricTile label="Calmar Ratio" value={result.calmar_ratio.toFixed(2)} />
                    <MetricTile
                      label="Max Drawdown"
                      value={formatPct(result.max_drawdown)}
                      color="negative"
                    />
                    <MetricTile label="Total Trades" value={result.total_trades.toString()} />
                    <MetricTile
                      label="Win Rate"
                      value={formatPct(result.win_rate)}
                      color={result.win_rate >= 0.5 ? 'positive' : 'negative'}
                    />
                    <MetricTile label="Profit Factor" value={result.profit_factor.toFixed(2)} />
                    <MetricTile
                      label="Best Trade"
                      value={formatPct(result.best_trade)}
                      color="positive"
                    />
                    <MetricTile
                      label="Worst Trade"
                      value={formatPct(result.worst_trade)}
                      color="negative"
                    />
                    <MetricTile label="Win/Loss" value={`${result.winning_trades}/${result.losing_trades}`} />
                    <MetricTile
                      label="Avg Duration"
                      value={`${result.avg_trade_duration_minutes.toFixed(0)}m`}
                    />
                  </div>
                ) : null}
              </CardContent>
            </Card>
          </div>
        </div>

        {/* Equity Curve */}
        {result && (
          <Card>
            <CardHeader>
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <CardTitle>Equity Curve</CardTitle>
                <div className="flex flex-wrap items-center gap-3 text-xs text-zinc-500">
                  <span>
                    {result.start_date.slice(0, 10)} → {result.end_date.slice(0, 10)}
                  </span>
                  <span className={cn(
                    'font-mono font-semibold',
                    result.total_return >= 0 ? 'text-emerald-400' : 'text-rose-400'
                  )}>
                    {result.total_return >= 0 ? '+' : ''}{formatPct(result.total_return)}
                  </span>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <ChartErrorBoundary chartName="Equity Curve">
                <EquityCurveChart
                  equityCurve={result.equity_curve}
                  initialCash={params.initial_cash}
                  height={350}
                />
              </ChartErrorBoundary>
            </CardContent>
          </Card>
        )}

        {/* Footer */}
        <div className="mt-8 text-center">
          <p className="text-xs text-zinc-600">
            Backtesting engine: vectorbt • {demoModeEnabled ? 'Running coherent demo session data for reviews' : 'Using current project backtest inputs'}
          </p>
        </div>
      </PageShell>
    </div>
  );
}

/**
 * MetricTile — Small result metric card.
 */
function MetricTile({
  label,
  value,
  color = 'default',
}: {
  label: string;
  value: string;
  color?: 'default' | 'positive' | 'negative';
}) {
  const valueColor =
    color === 'positive'
      ? 'text-emerald-400'
      : color === 'negative'
        ? 'text-rose-400'
        : 'text-zinc-100';

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
      <p className="text-xs text-zinc-500 mb-1">{label}</p>
      <p className={cn('text-lg font-bold font-mono', valueColor)}>{value}</p>
    </div>
  );
}
