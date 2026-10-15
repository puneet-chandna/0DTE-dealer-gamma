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
  fees: number;
  slippage: number;
  position_size: number;
  execution_delay_bars: number;
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

function formatRatio(value: number | null): string {
  return value === null ? '—' : value.toFixed(2);
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
    start_date: getCurrentMarketDateString(),
    end_date: getCurrentMarketDateString(),
    entry_threshold: -1e9,
    exit_threshold: 0,
    initial_cash: 100000,
    fees: 0.001,
    slippage: 0.001,
    position_size: 1,
    execution_delay_bars: 1,
  });

  const [runState, dispatchRun] = useReducer(backtestRunReducer, {
    submitted: null,
    runEnabled: false,
  });
  const autoStartedDemoRef = useRef(false);

  const { data: result, isLoading, error, isFetching, refetch } = useVectorbtBacktest(
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
    if (futureDateError || !params.start_date || !params.end_date || params.start_date > params.end_date) {
      return;
    }

    if (JSON.stringify(params) === JSON.stringify(runState.submitted)) {
      void refetch();
      return;
    }

    dispatchRun({ type: 'submit', params });
  }, [futureDateError, params, refetch, runState.submitted]);

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
            Directional long-underlying simulation. Signals execute at a later close; costs and fills are assumptions.
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
              <form onSubmit={(event) => { event.preventDefault(); if (event.currentTarget.checkValidity()) handleRun(); }} className="space-y-5">
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
                    required
                    max={params.end_date || marketToday}
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
                    required
                    min={params.start_date}
                    max={marketToday}
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
                <label htmlFor="backtest-entry" className="text-xs font-medium text-zinc-400 block mb-1.5">
                  Entry Threshold (GEX $)
                </label>
                <input
                  id="backtest-entry"
                  required
                  type="number"
                  value={params.entry_threshold}
                  onChange={(e) =>
                    setParams((p) => ({ ...p, entry_threshold: Number(e.target.value) }))
                  }
                  className="w-full rounded-lg border border-zinc-700 bg-zinc-800/60 px-3 py-2 text-sm text-zinc-200 focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500/30 font-mono"
                  step="any"
                />
                <p className="mt-1 text-xs text-zinc-500">Enter long when GEX drops below this</p>
              </div>

              <div>
                <label htmlFor="backtest-exit" className="text-xs font-medium text-zinc-400 block mb-1.5">
                  Exit Threshold (GEX $)
                </label>
                <input
                  id="backtest-exit"
                  required
                  type="number"
                  value={params.exit_threshold}
                  onChange={(e) =>
                    setParams((p) => ({ ...p, exit_threshold: parseFloat(e.target.value) || 0 }))
                  }
                  className="w-full rounded-lg border border-zinc-700 bg-zinc-800/60 px-3 py-2 text-sm text-zinc-200 focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500/30 font-mono"
                  step="any"
                />
              </div>

              <div>
                <label htmlFor="backtest-cash" className="text-xs font-medium text-zinc-400 block mb-1.5">
                  Initial Cash
                </label>
                <input
                  id="backtest-cash"
                  required
                  min={1}
                  type="number"
                  value={params.initial_cash}
                  onChange={(e) =>
                    setParams((p) => ({ ...p, initial_cash: Number(e.target.value) }))
                  }
                  className="w-full rounded-lg border border-zinc-700 bg-zinc-800/60 px-3 py-2 text-sm text-zinc-200 focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500/30 font-mono"
                  step="any"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                {([
                  { key: 'fees', label: 'Fee per side (%)', scale: 100, min: 0, max: 99, step: 0.01 },
                  { key: 'slippage', label: 'Spread/slippage per side (%)', scale: 100, min: 0, max: 99, step: 0.01 },
                  { key: 'position_size', label: 'Allocation (%)', scale: 100, min: 1, max: 100, step: 1 },
                  { key: 'execution_delay_bars', label: 'Execution delay (bars)', scale: 1, min: 1, max: 30, step: 1 },
                ] as const).map(({ key, label, scale, ...bounds }) => (
                  <div key={key}>
                    <label htmlFor={`backtest-${key}`} className="block text-xs text-zinc-400 mb-1.5">{label}</label>
                    <input id={`backtest-${key}`} type="number" required {...bounds}
                      value={params[key] * scale}
                      onChange={(event) => setParams((previous) => ({ ...previous, [key]: Number(event.target.value) / scale }))}
                      className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100" />
                  </div>
                ))}
              </div>

              {/* Run Button */}
              <button
                type="submit"
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
              </form>

              {error && !futureDateError && (
                <div role="alert" className="rounded-lg border border-rose-500/20 bg-rose-500/10 px-3 py-2 text-xs text-rose-400">
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
                {result?.provenance && (
                  <section aria-label="Data provenance" className="mb-4 space-y-2 text-xs text-zinc-400">
                    <p className="font-medium text-zinc-200">
                      {result.provenance.actual_instrument}{result.provenance.is_proxy ? ' · SPX proxy' : ''}
                    </p>
                    <p>{result.provenance.sample_count} {result.provenance.data_kind} observations · {result.provenance.provider}</p>
                    {result.provenance.actual_start && result.provenance.actual_end && (
                      <p>Actual coverage: {result.provenance.actual_start.slice(0, 10)} to {result.provenance.actual_end.slice(0, 10)}</p>
                    )}
                    {result.closed_trades !== undefined && <p>{result.closed_trades} closed · {result.open_trades ?? 0} open · trade statistics use closed trades</p>}
                    {result.fees !== undefined && result.slippage !== undefined && (
                      <p>Assumptions: fee {formatPct(result.fees)} / side · spread/slippage {formatPct(result.slippage)} / side · delay {result.execution_delay_bars} bars</p>
                    )}
                    <details>
                      <summary className="cursor-pointer">Data and simulation limitations</summary>
                      <ul className="mt-2 list-disc pl-4 space-y-1">
                        {result.provenance.quality_limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}
                      </ul>
                    </details>
                  </section>
                )}
                {!result && !isRunning ? (
                  <div className="flex min-h-[220px] items-center justify-center sm:min-h-[280px] lg:min-h-[340px]">
                    <div className="text-center">
                      <p className="text-sm text-zinc-500">Configure parameters and run a backtest</p>
                      <p className="mt-1 text-xs text-zinc-600">
                        Strategy: Long when Net GEX {'<'} entry threshold, exit when {'>'} exit threshold
                        {' '}• Long-only • Requires captured history or explicit demo mode
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
                    <MetricTile label="Sharpe Ratio" value={formatRatio(result.sharpe_ratio)} />
                    <MetricTile label="Sortino Ratio" value={formatRatio(result.sortino_ratio)} />
                    <MetricTile label="Calmar Ratio" value={formatRatio(result.calmar_ratio)} />
                    <MetricTile
                      label="Max Drawdown"
                      value={formatPct(result.max_drawdown)}
                      color="negative"
                    />
                    <MetricTile label="Entries" value={result.total_trades.toString()} />
                    <MetricTile
                      label="Win Rate"
                      value={formatPct(result.win_rate)}
                      color={result.win_rate >= 0.5 ? 'positive' : 'negative'}
                    />
                    <MetricTile label="Profit Factor" value={formatRatio(result.profit_factor)} />
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
                  initialCash={result.initial_cash ?? runState.submitted?.initial_cash ?? 100000}
                  timestamps={result.equity_timestamps}
                  height={350}
                />
              </ChartErrorBoundary>
            </CardContent>
          </Card>
        )}

        {/* Footer */}
        <div className="mt-8 text-center">
          <p className="text-xs text-zinc-600">
            Backtesting engine: vectorbt • {result?.provenance?.data_kind === 'synthetic' ? 'Synthetic demo; no market evidence' : 'Captured history required; results depend on data quality'}
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
