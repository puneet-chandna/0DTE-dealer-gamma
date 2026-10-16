import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { HedgingCascadeSimulator } from './HedgingCascadeSimulator';
import type { GEXSnapshot } from '@/types';

const snapshot = (gex: number, spot = 100): GEXSnapshot => ({
  timestamp: '2026-03-30T16:00:00Z',
  net_gex: gex,
  total_call_gex: Math.max(gex, 0),
  total_put_gex: Math.min(gex, 0),
  zero_gamma_level: 100,
  spot_price: spot,
  dominant_strike: 100,
  gex_by_strike: { 100: gex },
  metrics: {},
});

function moveSlider(move: number) {
  fireEvent.change(screen.getByRole('slider'), { target: { value: move } });
}

function summaryValue(label: string) {
  return screen.getByText(label).parentElement!;
}

describe('HedgingCascadeSimulator', () => {
  it.each([
    [1e6, 1, 'Dealers SELL'],
    [1e6, -1, 'Dealers BUY'],
    [-1e6, 1, 'Dealers BUY'],
    [-1e6, -1, 'Dealers SELL'],
  ])('shows the hedge sign and dollar units for GEX %s and move %s', (gex, move, action) => {
    render(<HedgingCascadeSimulator data={snapshot(gex)} />);
    moveSlider(move);

    // At S=100, GEX=$1M per 1% move: a one-point move needs a $1M opposite hedge.
    const notional = screen.getAllByText('$1M')[0];
    expect(within(notional.parentElement!).getByText(action)).toBeInTheDocument();
  });

  it.each([
    [1e9, 1, '0.67×', '+0.7 pts', /dampened/i],
    [1e9, -1, '0.67×', '-0.7 pts', /dampened/i],
    [-1e9, 1, '1.98×', '+2.0 pts', /amplifying/i],
    [-1e9, -1, '1.98×', '-2.0 pts', /amplifying/i],
  ])('sums signed impacts for GEX %s and move %s', (gex, move, ratio, total, status) => {
    render(<HedgingCascadeSimulator data={snapshot(gex)} />);
    moveSlider(move);

    // Feedback is ±0.5: 1 ± .5 + .25 ± .125 + .0625 ± .03125 + .015625.
    expect(within(summaryValue('Signed move ratio')).getByText(ratio)).toBeInTheDocument();
    expect(within(summaryValue('After cascade')).getByText(total)).toBeInTheDocument();
    expect(screen.getByText(status)).toBeInTheDocument();
  });

  it('names the shock slider and announces its unit', () => {
    render(<HedgingCascadeSimulator data={snapshot(1e6)} />);
    const slider = screen.getByRole('slider', { name: /hypothetical spx move \(points\)/i });
    expect(slider).toHaveAttribute('aria-valuetext', '0 points');
    fireEvent.change(slider, { target: { value: 1 } });
    expect(slider).toHaveAttribute('aria-valuetext', '+1 points');
  });

  it('sums snapshot GEX without reweighting it by strike distance', () => {
    const data = snapshot(1e6, 200);
    data.gex_by_strike = { 100: 2e6, 300: -1e6 };
    render(<HedgingCascadeSimulator data={data} />);
    moveSlider(2);
    // Two points is 1% of S=200: the net $1M/1% exposure requires a $1M sell hedge.
    const notional = screen.getAllByText('$1M')[0];
    expect(within(notional.parentElement!).getByText('Dealers SELL')).toBeInTheDocument();
  });

  it('shows no trade for zero GEX and an unchanged shock', () => {
    render(<HedgingCascadeSimulator data={snapshot(0)} />);
    moveSlider(1);
    expect(screen.getByText('No hedge adjustment')).toBeInTheDocument();
    expect(within(summaryValue('After cascade')).getByText('+1.0 pts')).toBeInTheDocument();
  });

  it('does not classify nonconvergent feedback as ordinary damping', () => {
    render(<HedgingCascadeSimulator data={snapshot(4e9)} />);
    moveSlider(1);
    expect(screen.getByText(/^unstable scenario$/i)).toBeInTheDocument();
    expect(screen.queryByText(/^dampened$/i)).not.toBeInTheDocument();
  });

  it('keeps zero shocks idle', () => {
    render(<HedgingCascadeSimulator data={snapshot(1e9)} />);
    expect(screen.queryByText('After cascade')).not.toBeInTheDocument();
    expect(screen.getByText(/drag the slider/i)).toBeInTheDocument();
  });

  it.each([Number.NaN, Number.POSITIVE_INFINITY, Number.MAX_VALUE])('does not display unsafe model results for GEX %s', (gex) => {
    render(<HedgingCascadeSimulator data={snapshot(gex)} />);
    moveSlider(1);
    expect(screen.getByText(/simulation unavailable/i)).toBeInTheDocument();
    expect(screen.queryByText('After cascade')).not.toBeInTheDocument();
  });

  it.each([0, -100, Number.NaN, Number.POSITIVE_INFINITY])('rejects unusable spot %s', (spot) => {
    render(<HedgingCascadeSimulator data={snapshot(1e6, spot)} />);
    moveSlider(1);
    expect(screen.getByText(/simulation unavailable/i)).toBeInTheDocument();
    expect(screen.queryByText('After cascade')).not.toBeInTheDocument();
  });
});
