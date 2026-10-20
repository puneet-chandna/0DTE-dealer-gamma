'use client';

import { useEffect, useRef, useState, useCallback, useReducer } from 'react';
import { NavBar } from '@/components/ui/NavBar';
import { DataContext } from '@/components/ui/DataContext';
import { Card, CardHeader, CardContent, CardTitle, PageShell } from '@/components/ui';
import { ChartErrorBoundary, EquityCurveChart } from '@/components/charts';
import { useVectorbtBacktest } from '@/hooks/useAnalyticsData';
import { cn, formatGEX, formatMarketTimestamp, getCurrentTradingDateString, isFutureMarketDate } from '@/lib/utils';
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
    start_date: getCurrentTradingDateString(),
    end_date: getCurrentTradingDateString(),
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

  const marketToday = getCurrentTradingDateString();
  const futureDateError =
    isFutureMarketDate(params.start_date, marketToday) ||
    isFutureMarketDate(params.end_date, marketToday)
      ? `Future dates aren't available for backtests. Choose a date on or before ${marketToday} (latest eligible weekday session).`
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
  const canRunBacktest = !isRunning && !futureDateError && !!params.start_date && !!params.end_date && params.start_date <= params.end_date;

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

  const draftChanged = runState.submitted !== null && JSON.stringify(params) !== JSON.stringify(runState.submitted);
  const closedTrades = result?.closed_trades ?? result?.total_trades ?? 0;
  const tradeStatsAvailable = closedTrades > 0;

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-50">
      <NavBar />

      <PageShell variant="wide">
        {/* Page Header */}
        <div className="page-heading"><div>
          <h1 className="text-2xl font-bold tracking-tight">Strategy Backtester</h1>
          <p className="mt-1 text-sm text-zinc-400">
            Directional long-underlying simulation. Signals execute at a later close; costs and fills are assumptions.
          </p>
        </div></div>

        {/* Controls + Results Row */}
        <div className="backtest-workspace">
          {/* Controls Panel */}
          <Card>
            <CardHeader>
              <CardTitle>Draft parameters</CardTitle>
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
                <p className="mt-1 text-xs text-zinc-500">Enter long below {formatGEX(params.entry_threshold)}</p>
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
                <p className="mt-1 text-xs text-zinc-500">Exit above {formatGEX(params.exit_threshold)}</p>
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
                className={cn('control-button primary w-full py-2.5 text-sm', isRunning && 'cursor-wait')}
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

          <div className="min-w-0 space-y-5">
            {draftChanged && result && <p role="status" className="research-alert">Parameters changed since last run. Results below use the submitted settings.</p>}
            <Card>
              <CardHeader><CardTitle>{result ? 'Equity Curve' : 'Results'}</CardTitle><span className="panel-caption">Long underlying · delayed-close execution</span></CardHeader>
              <CardContent>
                {isRunning ? <div className="empty-chart" role="status">Running backtest with submitted parameters…</div> : result ? <>
                  <DataContext provenance={result.provenance} />
                  <p className="mt-3 text-sm text-zinc-300">Actual coverage: {formatMarketTimestamp(result.provenance?.actual_start ?? result.start_date)} → {formatMarketTimestamp(result.provenance?.actual_end ?? result.end_date)}</p>
                  <p className="panel-caption mt-2">{closedTrades} closed · {result.open_trades ?? 0} open · trade statistics use closed trades</p>
                  <div className="mt-5"><ChartErrorBoundary chartName="Equity curve"><EquityCurveChart equityCurve={result.equity_curve} initialCash={result.initial_cash ?? runState.submitted?.initial_cash ?? 100000} timestamps={result.equity_timestamps} height={280} /></ChartErrorBoundary></div>
                  <details className="source-details mt-3"><summary>Submitted parameters & execution assumptions</summary>
                    {runState.submitted && <dl className="definition-list mt-3">
                      <dt>Requested dates</dt><dd>{runState.submitted.start_date} → {runState.submitted.end_date}</dd>
                      <dt>Entry / exit GEX</dt><dd>{formatGEX(runState.submitted.entry_threshold)} / {formatGEX(runState.submitted.exit_threshold)}</dd>
                      <dt>Initial cash</dt><dd>${runState.submitted.initial_cash.toLocaleString()}</dd>
                      <dt>Allocation</dt><dd>{formatPct(runState.submitted.position_size)}</dd>
                    </dl>}
                    <p>Assumptions: fee {formatPct(result.fees ?? runState.submitted?.fees ?? 0.001)} / side · spread/slippage {formatPct(result.slippage ?? runState.submitted?.slippage ?? 0.001)} / side · delay {result.execution_delay_bars ?? runState.submitted?.execution_delay_bars ?? 1} bars</p>
                  </details>
                </> : <div className="empty-chart"><p>Configure parameters and run a backtest</p><p className="panel-caption">Long when net GEX falls below entry; exit above the exit threshold. Captured history or explicit Demo mode is required.</p></div>}
              </CardContent>
            </Card>
            {result && !isRunning && <Card><CardHeader><CardTitle>Run statistics</CardTitle><span className="panel-caption">{result.provenance?.data_kind === 'synthetic' ? 'Synthetic scenario; no market evidence' : 'Descriptive results for the coverage above'}</span></CardHeader><CardContent>
              {!tradeStatsAvailable && <p className="research-alert mb-4">No closed trades; trade statistics are unavailable.</p>}
              <div className="result-metrics">
                <MetricTile label="Total Return" value={formatPct(result.total_return)} color={result.total_return >= 0 ? 'positive' : 'negative'} />
                <MetricTile label="Max Drawdown" value={formatPct(result.max_drawdown)} color="negative" />
                <MetricTile label="Entries" value={String(result.total_trades)} />
                <MetricTile label="Win Rate" value={tradeStatsAvailable ? formatPct(result.win_rate) : '—'} />
                <MetricTile label="Sharpe · annualized" value={formatRatio(result.sharpe_ratio)} />
                <MetricTile label="Sortino · annualized" value={formatRatio(result.sortino_ratio)} />
                <MetricTile label="Calmar · annualized" value={formatRatio(result.calmar_ratio)} />
                <MetricTile label="Profit Factor" value={tradeStatsAvailable ? formatRatio(result.profit_factor) : '—'} />
                <MetricTile label="Best Trade" value={tradeStatsAvailable ? formatPct(result.best_trade) : '—'} />
                <MetricTile label="Worst Trade" value={tradeStatsAvailable ? formatPct(result.worst_trade) : '—'} />
                <MetricTile label="Win/Loss" value={tradeStatsAvailable ? `${result.winning_trades}/${result.losing_trades}` : '—'} />
                <MetricTile label="Avg Duration" value={tradeStatsAvailable ? `${result.avg_trade_duration_minutes.toFixed(0)}m` : '—'} />
              </div>
              <p className="panel-caption mt-4">Annualized ratios can be extreme or undefined on short samples. Coverage, data provenance and execution assumptions limit interpretation.</p>
            </CardContent></Card>}
          </div>
        </div>
        <p className="panel-caption mt-5">Dates follow the backend’s weekday session convention; holidays are not resolved. Backtesting engine: vectorbt · Directional long-underlying simulation. These results do not model option strategy P&amp;L or establish future performance.</p>
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
    <div className="border-b border-zinc-800 pb-3">
      <p className="text-xs text-zinc-500 mb-1">{label}</p>
      <p className={cn('text-lg font-medium tabular-nums', valueColor)}>{value}</p>
    </div>
  );
}
