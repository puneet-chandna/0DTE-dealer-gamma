import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Area, AreaChart, Bar, BarChart, ReferenceLine, Scatter, Tooltip, XAxis, YAxis } from 'recharts';
import { GEXBarChart } from './GEXBarChart';
import { TimeSeriesChart } from './TimeSeriesChart';
import { IVSurfaceChart } from './IVSurfaceChart';
import { IVSkewChart } from './IVSkewChart';
import { EquityCurveChart } from './EquityCurveChart';
import { GammaDecayClock } from './GammaDecayClock';
import { HiddenFlowsPanel } from '../dashboard/HiddenFlowsPanel';
import { MomentumGauge } from './MomentumGauge';
import { GammaMagnetField } from '../dashboard/GammaMagnetField';
import type { GEXSnapshot } from '@/types';

vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  AreaChart: vi.fn(({ children }: React.PropsWithChildren) => <svg>{children}</svg>),
  BarChart: vi.fn(({ children }: React.PropsWithChildren) => <div>{children}</div>),
  ScatterChart: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  ComposedChart: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  Area: vi.fn(() => null), Bar: vi.fn(() => null), Scatter: vi.fn(() => null),
  Line: vi.fn(() => null), Cell: () => null, XAxis: vi.fn(() => null), YAxis: vi.fn(() => null),
  ReferenceLine: vi.fn(() => null), CartesianGrid: () => null, Tooltip: vi.fn(() => null),
}));

const snapshot: GEXSnapshot = {
  timestamp: '2026-03-30T19:30:00Z', spot_price: 100,
  net_gex: 1e9, total_call_gex: 2e9, total_put_gex: -1e9,
  zero_gamma_level: 100.5, dominant_strike: 100,
  gex_by_strike: { 98: 2e9, 102: -1e9 }, metrics: { zero_gamma_crossing_found: true },
};

beforeEach(() => vi.clearAllMocks());

describe('workstation chart coordinates', () => {
  it('uses numeric strikes, a named near-spot range and exact fractional reference levels', () => {
    const data = [50, 99, 100, 101, 150].map((strike) => ({ strike, gex: 1e9, gexBillions: 1 }));
    render(<GEXBarChart data={data} spotPrice={100.25} zeroGammaLevel={100.75} />);
    expect(screen.getByRole('group', { name: 'Strike range' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /near spot/i })).toHaveAttribute('aria-pressed', 'true');
    expect(vi.mocked(BarChart).mock.calls.at(-1)![0].data).toHaveLength(3);
    expect(vi.mocked(XAxis).mock.calls.at(-1)![0]).toMatchObject({ type: 'number', dataKey: 'strike' });
    const references = vi.mocked(ReferenceLine).mock.calls.map(([props]) => props);
    expect(references).toEqual(expect.arrayContaining([expect.objectContaining({ x: 100.25 }), expect.objectContaining({ x: 100.75 })]));
    expect(screen.getByText(/full-chain totals unchanged/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Full chain' }));
    expect(vi.mocked(BarChart).mock.calls.at(-1)![0].data).toHaveLength(5);
    expect(data).toHaveLength(5);
    expect(vi.mocked(Bar).mock.calls.at(-1)![0].isAnimationActive).toBe(false);
  });

  it('keeps strike bars synchronized with a newly received capture', () => {
    const { rerender } = render(<GEXBarChart data={[{ strike: 100, gex: 1e9, gexBillions: 1 }]} spotPrice={100} />);
    rerender(<GEXBarChart data={[{ strike: 100, gex: -3e9, gexBillions: -3 }]} spotPrice={100.5} />);
    expect(vi.mocked(BarChart).mock.calls.at(-1)![0].data).toEqual([{ strike: 100, gex: -3e9, gexBillions: -3 }]);
  });

  it('keeps GEX tick spacing symmetric around a labelled zero without changing the domain', () => {
    render(<GEXBarChart data={[{ strike: 100, gex: -2.327e9, gexBillions: -2.327 }]} spotPrice={100} />);
    const axis = vi.mocked(YAxis).mock.calls.at(-1)![0];
    expect(axis.ticks).toEqual([-2, -1, 0, 1, 2]);
    expect(axis.domain).toEqual([-2.327 * 1.1, 2.327 * 1.1]);
  });

  it.each([
    ['2026-03-30T14:04:59Z', '10:00:01', '10:00:08'],
    ['2026-03-30T14:05:01Z', '10:00', '10:00'],
  ])('uses second precision only for capture spans under five minutes: %s', (lastCapture, firstLabel, nextLabel) => {
    render(<TimeSeriesChart data={[
      { timestamp: '2026-03-30T14:00:01Z', netGex: 1e9, netGexBillions: 1 },
      { timestamp: lastCapture, netGex: 2e9, netGexBillions: 2 },
    ]} />);
    const formatTick = vi.mocked(XAxis).mock.calls.at(-1)![0].tickFormatter!;
    expect(formatTick(Date.parse('2026-03-30T14:00:01Z'), 0)).toBe(firstLabel);
    expect(formatTick(Date.parse('2026-03-30T14:00:08Z'), 1)).toBe(nextLabel);
    const tooltip = vi.mocked(Tooltip).mock.calls.at(-1)![0];
    expect(tooltip.labelFormatter!(Date.parse('2026-03-30T14:00:01Z'), [])).toBe('Mar 30, 2026 10:00 AM ET');
  });

  it('spaces captures by elapsed time and breaks the plot only when a gap exceeds five minutes', () => {
    render(<TimeSeriesChart data={[
      { timestamp: '2026-03-30T14:16:00Z', netGex: 3e9, netGexBillions: 3 },
      { timestamp: '2026-03-30T14:00:00Z', netGex: 1e9, netGexBillions: 1 },
      { timestamp: '2026-03-30T14:05:00Z', netGex: 2e9, netGexBillions: 2 },
    ]} />);
    const plotted = vi.mocked(AreaChart).mock.calls.at(-1)![0].data as Array<{ time: number; netGexBillions: number | null }>;
    expect(plotted).toHaveLength(4);
    expect(plotted.map((row) => row.time)).toEqual([
      Date.parse('2026-03-30T14:00:00Z'), Date.parse('2026-03-30T14:05:00Z'),
      Date.parse('2026-03-30T14:10:30Z'), Date.parse('2026-03-30T14:16:00Z'),
    ]);
    expect(plotted[2].netGexBillions).toBeNull();
    expect(vi.mocked(XAxis).mock.calls.at(-1)![0]).toMatchObject({ type: 'number', dataKey: 'time' });
    expect(vi.mocked(Area).mock.calls.at(-1)![0]).toMatchObject({ connectNulls: false, isAnimationActive: false, type: 'linear' });
    expect(screen.getByText(/gaps over 5 minutes/i)).toBeInTheDocument();
  });

  it('labels relative moneyness and puts ATM at zero with named call and put series', () => {
    render(<IVSurfaceChart data={[
      { strike: 100, type: 'call', iv: 0.2, mid_price: 1, moneyness: 0 },
      { strike: 90, type: 'put', iv: 0.3, mid_price: 2, moneyness: -0.1 },
    ]} />);
    expect(vi.mocked(XAxis).mock.calls.at(-1)![0].label).toMatchObject({ value: 'Relative moneyness (K−S)/S' });
    expect(vi.mocked(ReferenceLine).mock.calls.at(-1)![0].x).toBe(0);
    expect(screen.getByText('Calls')).toBeInTheDocument();
    expect(screen.getByText('Puts')).toBeInTheDocument();
    expect(vi.mocked(Scatter).mock.calls.every(([props]) => props.isAnimationActive === false)).toBe(true);
  });

  it('anchors IV-smile ticks at ATM and keeps its label inside the plotting region', () => {
    render(<IVSurfaceChart data={[
      { strike: 81, type: 'call', iv: 0.2, mid_price: 1, moneyness: -0.19 },
      { strike: 119, type: 'put', iv: 0.3, mid_price: 2, moneyness: 0.19 },
    ]} />);
    const axis = vi.mocked(XAxis).mock.calls.at(-1)![0];
    expect(axis.ticks).toHaveLength(7);
    [-0.15, -0.1, -0.05, 0, 0.05, 0.1, 0.15].forEach((value, index) => expect(axis.ticks![index]).toBeCloseTo(value));
    expect(axis.tickFormatter!(0, 3)).toBe('0%');
    expect(vi.mocked(ReferenceLine).mock.calls.at(-1)![0]).toMatchObject({ x: 0, label: { position: 'insideTopLeft' } });
  });

  it('uses a numeric strike axis and percentage-point units for IV skew', () => {
    render(<IVSkewChart data={[{ strike: 100, skew: 0.02, call_iv: 0.2, put_iv: 0.22, moneyness: 0 }]} />);
    expect(vi.mocked(XAxis).mock.calls.at(-1)![0].type).toBe('number');
    expect(vi.mocked(YAxis).mock.calls.at(-1)![0].label).toMatchObject({ value: 'Put − call IV (pp)' });
  });

  it('keeps nearby equity axis labels distinct and spaces actual timestamps numerically', () => {
    render(<EquityCurveChart equityCurve={[100000, 100250]} initialCash={100000} timestamps={['2026-03-30T14:00:00Z', '2026-03-30T15:00:00Z']} />);
    const axis = vi.mocked(YAxis).mock.calls.at(-1)![0];
    expect(axis.tickFormatter!(100000, 0)).not.toBe(axis.tickFormatter!(100250, 1));
    expect(vi.mocked(XAxis).mock.calls.at(-1)![0]).toMatchObject({ type: 'number', dataKey: 'time' });
    expect(vi.mocked(Area).mock.calls.at(-1)![0].isAnimationActive).toBe(false);
  });
});

describe('qualified static model panels', () => {
  it('uses the captured clock date and an uncapped fixed-volatility time factor', () => {
    const { container } = render(<GammaDecayClock data={snapshot} />);
    expect(screen.getByText('Fixed-volatility ATM time factor')).toBeInTheDocument();
    expect(screen.getByText(/snapshot clock: mar 30, 2026 3:30 pm et/i)).toBeInTheDocument();
    expect(screen.getByText('3.61×')).toBeInTheDocument();
    expect(screen.getByText(/16:00 ET/i)).toBeInTheDocument();
    expect(screen.queryByText(/danger|critical|stable|dies to zero/i)).not.toBeInTheDocument();
    expect(container.querySelector('animate')).toBeNull();
  });

  it('treats a zero hidden-flow scenario as no net adjustment', () => {
    render(<HiddenFlowsPanel data={{ charm_flow: 0, vanna_flow: 0, net_hidden_flow: 0, charm_by_strike: {}, vanna_by_strike: {} }} />);
    expect(screen.getByText('No net adjustment')).toBeInTheDocument();
    expect(screen.queryByText('Buy scenario')).not.toBeInTheDocument();
  });

  it('keeps the final seconds distinguishable from expiry', () => {
    render(<GammaDecayClock data={{ ...snapshot, timestamp: '2026-10-16T19:59:59Z' }} />);
    expect(screen.getByText('<1m')).toBeInTheDocument();
    expect(screen.getByText('152.97×')).toBeInTheDocument();
  });

  it.each(['invalid', '2026-03-30T13:00:00Z', '2026-03-29T19:30:00Z'])('keeps the time factor unavailable outside a valid weekday illustration: %s', (timestamp) => {
    render(<GammaDecayClock data={{ ...snapshot, timestamp }} />);
    expect(screen.getByText('Outside illustration interval')).toBeInTheDocument();
    expect(screen.queryByText(/NaN|Infinity/)).not.toBeInTheDocument();
  });

  it('does not report zero gamma at or after the assumed close', () => {
    render(<GammaDecayClock data={{ ...snapshot, timestamp: '2026-03-30T20:00:00Z' }} />);
    expect(screen.getByText('Outside illustration interval')).toBeInTheDocument();
    expect(screen.queryByText('0.00×')).not.toBeInTheDocument();
  });

  it('renders signed concentration and preserves the original positive-GEX weighting without prediction or motion', () => {
    const { container } = render(<GammaMagnetField data={snapshot} />);
    expect(screen.getByText('GEX concentration')).toBeInTheDocument();
    expect(screen.getByText('Weighted positive-GEX level')).toBeInTheDocument();
    expect(screen.getByText('$98.00')).toBeInTheDocument();
    expect(screen.getByText(/\+\$2.00B/)).toBeInTheDocument();
    expect(screen.getByText(/−\$1.00B/)).toBeInTheDocument();
    expect(screen.queryByText(/attractor|repeller|pull toward/i)).not.toBeInTheDocument();
    expect(container.querySelector('animate, filter')).toBeNull();
  });

  it('keeps an unavailable zero-gamma crossing explicit rather than showing a candidate price as a level', () => {
    render(<GammaMagnetField data={{ ...snapshot, metrics: { zero_gamma_crossing_found: false, zero_gamma_relation: 'above_range' } }} />);
    expect(screen.getByText('Above Range')).toBeInTheDocument();
    expect(screen.queryByText('$100.50')).not.toBeInTheDocument();
  });

  it('uses the preserved distance weights across positive levels and excludes negative GEX from the weighted level', () => {
    render(<GammaMagnetField data={{ ...snapshot, gex_by_strike: { 90: 1e9, 105: 2e9, 110: -3e9 } }} />);
    const weightA = 1e9 / Math.pow(15, 1.5);
    const weightB = 2e9 / Math.pow(10, 1.5);
    const weighted = (90 * weightA + 105 * weightB) / (weightA + weightB);
    expect(screen.getByText(`$${weighted.toFixed(2)}`)).toBeInTheDocument();
    expect(screen.getByText('50.0%')).toBeInTheDocument();
  });

  it('keeps signed hidden-flow dollars and score meaning visible without animated bars or a pulsing gauge', () => {
    const { container } = render(<>
      <HiddenFlowsPanel data={{ charm_flow: -1e6, vanna_flow: 2e6, net_hidden_flow: 1e6, charm_by_strike: {}, vanna_by_strike: {} }} />
      <MomentumGauge data={{ call_intensity: 1.2, put_intensity: 0.4, net_toxicity: 0.8, squeeze_score: 0.7 }} />
    </>);
    expect(screen.getByText('−$1.0M')).toBeInTheDocument();
    expect(screen.getByText('+$2.0M')).toBeInTheDocument();
    expect(screen.getByText(/this score is not a probability/i)).toBeInTheDocument();
    expect(container.querySelector('animate, [class*="duration-700"], [class*="animate-pulse"]')).toBeNull();
  });
});
